#!/usr/bin/env bash
# Déploiement de l'API Rempart sur AWS, **avec la preuve du déploiement**.
#
# Le script ne se contente pas de dire « déployé » : à la fin, il affiche ce
# qui est RÉELLEMENT en place côté AWS — commit déployé, date de mise à jour de
# la Lambda, route OPTIONS sans authorisateur, réponse réelle du preflight,
# variables d'environnement posées. Un déploiement dont la preuve ne tient pas
# est un déploiement à refaire.
#
# Prérequis : aws_cdk disponible dans un Python (le python système ne l'a pas),
# credentials AWS valides, layer Lambda construit si absent.
#
# Usage :
#   PATH="$PWD/../.venv/bin:$PATH" bash scripts/deploy_api.sh
#   bash scripts/deploy_api.sh --synth-only   # n Synthesis pas de déploiement
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IAC_DIR="${REPO_ROOT}/iac/control-plane"
REGION="${REGION:-eu-north-1}"
ACCOUNT="${ACCOUNT:-710332178565}"
API_ID="${API_ID:-qm6dmdkgdg}"
PORTAL_ORIGIN="${PORTAL_ORIGIN:-https://d1o2xnfrq8xomh.cloudfront.net}"
AWS="${AWS:-$HOME/.local/bin/aws}"
# Clé du modèle de triage : NOM du paramètre SSM SecureString, jamais sa valeur.
#
# PIÈGE MESURÉ (14/11/2026) : ce paramètre conditionne à la fois la variable
# d'environnement de la Lambda de triage ET son droit `ssm:GetParameter`
# (voir stacks/orchestrator.py::_grant_llm_key_read). Oublié au déploiement,
# rien ne casse : la Lambda tourne, le triage retombe **silencieusement** sur le
# règleur déterministe, et la production n'a plus de vrai modèle. D'où un défaut
# ici, pas un avertissement : la valeur par défaut est le paramètre de
# production, et son existence est vérifiée avant le changeset.
LLM_KEY_PARAM="${REMPART_LLM_API_KEY_SSM_PARAM:-/rempart/prod/llm-key}"
export REMPART_LLM_API_KEY_SSM_PARAM="$LLM_KEY_PARAM"
# L'orchestrateur est inclus : l'intake des failles (`collect_findings`) et
# l'agent de triage y vivent, pas dans la Lambda API.
STACKS=("RempartStorageStack" "RempartApiStack" "RempartOrchestratorStack")

export CDK_DEFAULT_ACCOUNT="$ACCOUNT"
export CDK_DEFAULT_REGION="$REGION"
export AWS_REGION="$REGION"

log() { printf '[deploy-api] %s\n' "$*"; }
fail() { log "ERREUR : $*" >&2; exit 1; }

[ -x "$AWS" ] || fail "aws CLI introuvable : $AWS"
[ -d "$IAC_DIR" ] || fail "dossier IaC introuvable : $IAC_DIR"
python3 -c "import aws_cdk" 2>/dev/null \
  || fail "aws_cdk absent du python utilisé (PATH=.../.venv/bin:\$PATH)"

SYNTH_ONLY=0
[ "${1:-}" = "--synth-only" ] && SYNTH_ONLY=1

# ---- Paramètre de la clé du modèle --------------------------------------------
# Le nom seul est passé au CDK : la valeur SecureString n'est jamais lue ni
# imprimée par le script. Un paramètre absent signifierait un triage sans modèle.
prove_llm_param_exists() {
  local name="$1"
  local found
  found="$("$AWS" ssm describe-parameters --region "$REGION" \
    --query "Parameters[?Name=='$name'].Name | [0]" --output text 2>/dev/null || echo '')"
  if [ "$found" = "$name" ]; then
    log "paramètre de la clé du modèle : $name (existe)"
  else
    fail "paramètre SSM '$name' introuvable : le triage tournerait sans modèle. Crée-le ou définis REMPART_LLM_API_KEY_SSM_PARAM."
  fi
}

if [ "$SYNTH_ONLY" != "1" ]; then
  prove_llm_param_exists "$LLM_KEY_PARAM"
fi

# ---- Layer Lambda -------------------------------------------------------------
# Les dépendances tierces (fpdf2, requests, strands) ne sont pas versionnées :
# sans layer, les Lambdas se déploient mais échouent à la première invocation
# (Runtime.ImportModuleError). On le construit donc si besoin.
if [ ! -d "${IAC_DIR}/lambda-layer/python" ]; then
  log "layer absent — construction (scripts/build_lambda_layer.sh)"
  bash "${REPO_ROOT}/scripts/build_lambda_layer.sh"
fi

# ---- Déploiement --------------------------------------------------------------
cd "$IAC_DIR"
if [ "$SYNTH_ONLY" = "1" ]; then
  log "synthèse seulement (aucun déploiement)"
  REMPART_ALLOW_MISSING_LAYER=1 cdk synth --no-version-reporting >/dev/null
  log "synthèse OK"
  exit 0
fi

log "déploiement : ${STACKS[*]}"
cdk deploy "${STACKS[@]}" --require-approval never

# ---- Preuve du déploiement ----------------------------------------------------
echo
log "== Preuve du déploiement =="
COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'inconnu')"
# Le code que l'on s'apprête à déployer doit être celui de main : un commit
# oublié sur un HEAD détaché (ou une branche non poussée) se voit ici avant
# d'écraser la production. C'est exactement ce qui a failli se produire le
# 12/11/2026 (deux correctifs déployés mais absents de main).
git -C "$REPO_ROOT" fetch -q origin main 2>/dev/null || true
if git -C "$REPO_ROOT" diff --quiet origin/main -- backend iac 2>/dev/null; then
  echo "  PREUVE OK               : le code à déployer est identique à main (backend + iac)"
else
  echo "  PREUVE ÉCHEC            : le code à déployer diffère de main (commit non fusionné)"
  git -C "$REPO_ROOT" diff --stat origin/main -- backend iac | tail -8
fi
FUNCTION_NAME="$("$AWS" lambda list-functions --region "$REGION" \
  --query "Functions[?starts_with(FunctionName, 'RempartApiStack-RempartApiFunction')].FunctionName | [0]" \
  --output text 2>/dev/null || echo '')"
LAST_MODIFIED="$("$AWS" lambda get-function-configuration --function-name "$FUNCTION_NAME" \
  --region "$REGION" --query 'LastModified' --output text 2>/dev/null || echo '')"
echo "  commit déployé          : $COMMIT"
echo "  Lambda API              : ${FUNCTION_NAME:-introuvable}"
echo "  mise à jour le          : ${LAST_MODIFIED:-inconnue}"

OPTIONS_AUTH="$("$AWS" apigatewayv2 get-routes --api-id "$API_ID" --region "$REGION" \
  --query "Items[?RouteKey=='OPTIONS /v1/{proxy+}'].AuthorizationType | [0]" --output text 2>/dev/null || echo '')"
echo "  route OPTIONS /v1/{proxy+} : AuthorizationType=${OPTIONS_AUTH:-absente}"
if [ "$OPTIONS_AUTH" = "NONE" ]; then
  echo "  PREUVE OK               : le preflight n'exige plus de jeton"
else
  echo "  PREUVE ÉCHEC            : le preflight exige encore un jeton"
fi

PREFLIGHT="$(timeout 60 curl -s -o /dev/null -w '%{http_code}' -X OPTIONS \
  "https://${API_ID}.execute-api.${REGION}.amazonaws.com/v1/tenants" \
  -H "Origin: ${PORTAL_ORIGIN}" -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization' || echo 000)"
echo "  preflight réel          : HTTP ${PREFLIGHT}"
if [ "$PREFLIGHT" = "204" ]; then
  echo "  PREUVE OK               : le navigateur peut appeler l'API depuis le portail"
else
  echo "  PREUVE ÉCHEC            : le navigateur ne peut pas appeler l'API"
fi

REM="REMPART_CORS_ALLOW_ORIGINS REMPART_REPORTS_BUCKET"
MISSING=""
for key in $REM; do
  "$AWS" lambda get-function-configuration --function-name "$FUNCTION_NAME" --region "$REGION" \
    --query "Environment.Variables.$key" --output text 2>/dev/null | grep -q . || MISSING="$MISSING $key"
done
if [ -z "$MISSING" ]; then
  echo "  PREUVE OK               : variables d'environnement posées ($REM)"
else
  echo "  PREUVE ÉCHEC            : variables manquantes :$MISSING"
fi

# Tâches de l'orchestrateur : leur code porte l'intake des failles (empreinte
# calculée sur l'emplacement réel) et la lecture des heures-tâches.
TASK_COUNT="$("$AWS" lambda list-functions --region "$REGION" \
  --query "length(Functions[?starts_with(FunctionName, 'RempartOrchestratorStack')])" \
  --output text 2>/dev/null || echo '?')"
echo "  Lambdas orchestrateur : $TASK_COUNT"

# ---- Preuve : le triage a bien un vrai modèle ---------------------------------
# Le câblage du modèle tient à UNE variable de déploiement qui pilote deux
# moitiés (la variable d'environnement de la Lambda qui trie, et le droit
# `ssm:GetParameter` sur son rôle). Son oubli est invisible : la fonction
# tourne, le règleur déterministe répond à la place du modèle, et rien ne
# signale que la production n'a plus d'agent LLM. Mesuré le 14/11/2026.
prove_llm_wiring() {
  local fn role rn p doc env_param ssm_ok='' kms_ok=''
  fn="$("$AWS" lambda list-functions --region "$REGION" \
    --query "Functions[?starts_with(FunctionName, 'RempartOrchestratorStack-LambdaDispatchTriage')].FunctionName | [0]" \
    --output text 2>/dev/null || echo '')"
  if [ -z "$fn" ] || [ "$fn" = "None" ]; then
    echo "  PREUVE ÉCHEC            : Lambda de triage introuvable (aucun vrai modèle possible)"
    return 0
  fi
  env_param="$("$AWS" lambda get-function-configuration --function-name "$fn" --region "$REGION" \
    --query 'Environment.Variables.REMPART_LLM_API_KEY_SSM_PARAM' --output text 2>/dev/null || echo '')"
  role="$("$AWS" lambda get-function-configuration --function-name "$fn" --region "$REGION" \
    --query 'Role' --output text 2>/dev/null || echo '')"
  rn="${role##*/}"
  for p in $("$AWS" iam list-role-policies --role-name "$rn" --query 'PolicyNames[]' --output text 2>/dev/null); do
    doc="$("$AWS" iam get-role-policy --role-name "$rn" --policy-name "$p" --query 'PolicyDocument' --output json 2>/dev/null || echo '{}')"
    case "$doc" in *ssm:GetParameter*) ssm_ok=1 ;; esac
    case "$doc" in *kms:Decrypt*) kms_ok=1 ;; esac
  done
  echo "  Lambda de triage      : $fn"
  echo "  paramètre de la clé   : ${env_param:-absent}"
  if [ "$env_param" = "$LLM_KEY_PARAM" ] && [ -n "$ssm_ok" ] && [ -n "$kms_ok" ]; then
    echo "  PREUVE OK               : le triage peut réellement lire la clé du modèle ($env_param)"
  else
    echo "  PREUVE ÉCHEC            : triage SANS modèle (variable=$env_param, ssm:GetParameter=${ssm_ok:-non}, kms:Decrypt=${kms_ok:-non})"
  fi
}

echo
log "== Preuve : le vrai modèle de triage est câblé =="
prove_llm_wiring
