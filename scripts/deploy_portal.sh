#!/usr/bin/env bash
# Déploiement du portail Rempart : build Vite → upload S3 → invalidation CloudFront.
# Idempotent et rejouable. Ne contient AUCUN secret (l'authentification AWS vient
# de la session/du profil local). Usage : bash scripts/deploy_portal.sh
set -euo pipefail

# ---- Variables (surchargeables par l'environnement) -------------------------
REGION="${REGION:-eu-north-1}"
BUCKET="${BUCKET:-rempartportalstack-portalbucketf34416c0-eekv0qxwomo8}"
DISTRIBUTION_ID="${DISTRIBUTION_ID:-EYN0KKBTR7INC}"
AWS="${AWS:-$HOME/.local/bin/aws}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORTAL_DIR="${REPO_ROOT}/portal"
# Auth Cognito RÉELLE activée le 12/11/2026 (EF-POR-01) : domaine gratuit
# https://rempart.auth.eu-north-1.amazoncognito.com + client public sans secret.
# Valeurs publiques (aucun secret), surchargeables par l'environnement.
# Mode démo : VITE_USE_MOCKS=1, et/ou vider VITE_COGNITO_CLIENT_ID et
# VITE_COGNITO_DOMAIN → le portail retombe sur le persona picker hors ligne
# (cognito.ts renvoie null). Voir docs/portal-deployment.md.
export VITE_USE_MOCKS="${VITE_USE_MOCKS:-0}"
export VITE_BASE_PATH="${VITE_BASE_PATH:-/}"
export VITE_API_URL="${VITE_API_URL:-https://qm6dmdkgdg.execute-api.eu-north-1.amazonaws.com}"
export VITE_COGNITO_DOMAIN="${VITE_COGNITO_DOMAIN:-https://rempart.auth.eu-north-1.amazoncognito.com}"
export VITE_COGNITO_CLIENT_ID="${VITE_COGNITO_CLIENT_ID:-7qr971kfs2jlj5i2d065mb1fbl}"
export VITE_COGNITO_REDIRECT_URI="${VITE_COGNITO_REDIRECT_URI:-https://d1o2xnfrq8xomh.cloudfront.net/}"

fail() { echo "ERREUR : $*" >&2; exit 1; }

# ---- Garde-fous --------------------------------------------------------------
[ -x "$AWS" ] || fail "AWS CLI introuvable ou non exécutable : $AWS"
[ -d "$PORTAL_DIR" ] || fail "dossier du portail introuvable : $PORTAL_DIR"
"$AWS" s3api head-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null 2>&1 \
  || fail "bucket S3 introuvable ou inaccessible : $BUCKET (déployez RempartPortalStack d'abord : cdk deploy RempartPortalStack)"

# ---- Build -------------------------------------------------------------------
echo "== Build du portail (VITE_USE_MOCKS=$VITE_USE_MOCKS, VITE_BASE_PATH=$VITE_BASE_PATH) =="
(cd "$PORTAL_DIR" && npm run build) || fail "build du portail (npm run build)"
[ -f "$PORTAL_DIR/dist/index.html" ] || fail "dist/index.html absent après le build"
# Routage SPA : 404.html identique à index.html (complète les error responses
# CloudFront 403/404 → /index.html déjà définies dans la stack).
cp "$PORTAL_DIR/dist/index.html" "$PORTAL_DIR/dist/404.html"

# ---- Upload ------------------------------------------------------------------
echo "== Upload vers s3://$BUCKET =="
# aws s3 sync devine les Content-Type d'après l'extension ; --delete retire les
# anciens assets hashés (rend le déploiement idempotent).
"$AWS" s3 sync "$PORTAL_DIR/dist/" "s3://$BUCKET" --region "$REGION" --delete \
  || fail "upload S3 (aws s3 sync)"

# ---- Invalidation CloudFront (optionnelle) -----------------------------------
if [ -n "$DISTRIBUTION_ID" ]; then
  echo "== Invalidation CloudFront $DISTRIBUTION_ID (/*) =="
  # 1000 chemins invalidés/mois gratuits : /* coûte 1 chemin.
  "$AWS" cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*" >/dev/null \
    && echo "invalidation demandée (propagation ~1-2 min)" \
    || echo "AVERTISSEMENT : invalidation échouée ; l'upload est fait, index.html peut rester en cache (TTL 24 h)"
else
  echo "== Invalidation ignorée (DISTRIBUTION_ID vide) ; index.html peut rester en cache (TTL 24 h) =="
fi

echo "OK — portail déployé : https://$("$AWS" cloudfront get-distribution --id "$DISTRIBUTION_ID" \
  --query 'Distribution.DomainName' --output text 2>/dev/null || echo "$DISTRIBUTION_ID (domaine à retrouver via aws cloudfront list-distributions)")"

# ---- Preuve du déploiement ----------------------------------------------------
# Un déploiement n'est « fait » que s'il est démontré : on compare l'empreinte
# du bundle LOCAL à celle du bundle RÉELLEMENT servi par CloudFront, et on
# affiche le commit déployé. Si les deux empreintes diffèrent, le site ne sert
# pas ce qu'on vient de construire — et ça se voit tout de suite.
echo "== Preuve du déploiement =="
COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'inconnu')"
LOCAL_BUNDLE="$(ls -1 "$PORTAL_DIR"/dist/assets/*.js 2>/dev/null | head -1)"
DIST_DOMAIN="$("$AWS" cloudfront get-distribution --id "$DISTRIBUTION_ID" --query 'Distribution.DomainName' --output text 2>/dev/null || echo '')"
if [ -n "$LOCAL_BUNDLE" ] && [ -n "$DIST_DOMAIN" ]; then
  LOCAL_NAME="$(basename "$LOCAL_BUNDLE")"
  LOCAL_SHA="$(sha256sum "$LOCAL_BUNDLE" | cut -d' ' -f1)"
  SERVED_HTML="$(timeout 60 curl -s "https://$DIST_DOMAIN/")"
  # On garde le chemin complet « assets/xxx.js » : sans le préfixe, l'URL
  # tomberait sur le fallback SPA et renverrait du HTML (faux hash).
  SERVED_NAME="$(printf '%s' "$SERVED_HTML" | grep -o 'assets/[A-Za-z0-9._-]*\.js' | head -1)"
  if [ -n "$SERVED_NAME" ]; then
    # `--compressed` : CloudFront sert le bundle compressé, on compare donc les
    # octets DÉcompressés à ceux du fichier local, sinon les empreintes ne
    # peuvent pas coïncider (faux négatif).
    SERVED_SHA="$(timeout 90 curl -s --compressed "https://$DIST_DOMAIN/$SERVED_NAME" | sha256sum | cut -d' ' -f1)"
  else
    SERVED_SHA="(bundle non référencé par index.html)"
  fi
  echo "  commit déployé      : $COMMIT"
  echo "  bundle local        : $LOCAL_NAME  sha256=$LOCAL_SHA"
  echo "  bundle servi (live) : ${SERVED_NAME:-inconnu}  sha256=$SERVED_SHA"
  if [ "$LOCAL_SHA" = "$SERVED_SHA" ]; then
    echo "  PREUVE OK           : le site sert exactement le bundle construit"
  else
    echo "  PREUVE ÉCHEC        : le site sert autre chose (cache CloudFront ?)"
  fi
  echo "  page en ligne       : HTTP $(timeout 30 curl -s -o /dev/null -w '%{http_code}' "https://$DIST_DOMAIN/")"
else
  echo "  PREUVE incomplète   : bundle local ou domaine CloudFront introuvable"
fi
