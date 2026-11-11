#!/usr/bin/env bash
# Construit le layer Lambda des dépendances tierces de Rempart.
#
# Le runtime Python 3.12 d'AWS Lambda fournit boto3/botocore, mais PAS fpdf2
# (rapports PDF), requests (tickets GitHub) ni strands-agents (agent de tri).
# Ces paquets doivent être empaquetés dans un layer, compilés pour la bonne
# plateforme : manylinux2014_x86_64 + CPython 3.12.
#
# Usage :
#   ./scripts/build_lambda_layer.sh          # construit iac/control-plane/lambda-layer/python/
#   ./scripts/build_lambda_layer.sh --clean  # repart de zéro
#
# Aucune dépendance Docker : pip télécharge les roues manylinux directement.
# Le résultat n'est PAS versionné (voir .gitignore) : il se reconstruit en CI
# ou sur le poste qui déploie.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYER_DIR="${REPO_ROOT}/iac/control-plane/lambda-layer"
PYTHON_TARGET="${LAYER_DIR}/python"
PLATFORM="manylinux2014_x86_64"
PYTHON_VERSION="3.12"

# Les paquets du layer. Gardés alignés sur backend/requirements-ci.txt,
# MINUS ce que le runtime Lambda fournit déjà (boto3, botocore, urllib3,
# s3transfer, jmespath, python-dateutil, six).
PACKAGES=(
  "fpdf2==2.9.0"
  "requests==2.34.2"
  "strands-agents==1.64.0"
)

PIP="pip3"
if [ -x "${REPO_ROOT}/.venv/bin/pip" ]; then
  PIP="${REPO_ROOT}/.venv/bin/pip"
fi

if [ "${1:-}" = "--clean" ]; then
  echo "[layer] nettoyage de ${LAYER_DIR}"
  rm -rf "${LAYER_DIR}"
fi

mkdir -p "${PYTHON_TARGET}"

echo "[layer] installation pour ${PLATFORM} / CPython ${PYTHON_VERSION}"
echo "[layer] paquets : ${PACKAGES[*]}"

# --only-binary=:all: évite de compiler quoi que ce soit localement ; si un
# paquet n'a pas de roue manylinux, pip échoue et on le voit tout de suite.
"${PIP}" install \
  --target "${PYTHON_TARGET}" \
  --platform "${PLATFORM}" \
  --python-version "${PYTHON_VERSION}" \
  --implementation cp \
  --only-binary=:all: \
  --upgrade \
  "${PACKAGES[@]}"

# Nettoyage : les caches et les métadonnées de test gonflent l'archive pour rien
# (la limite d'un layer dézippé est de 250 Mo).
find "${PYTHON_TARGET}" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_TARGET}" -type d -name "tests" -prune -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_TARGET}" -type d -name "*.dist-info" -prune -exec rm -rf {} + 2>/dev/null || true

SIZE="$(du -sh "${PYTHON_TARGET}" | cut -f1)"
COUNT="$(find "${PYTHON_TARGET}" -maxdepth 1 -mindepth 1 | wc -l)"
echo "[layer] terminé : ${PYTHON_TARGET} (${SIZE}, ${COUNT} entrées de premier niveau)"
echo "[layer] vérification des imports attendus :"
for mod in fpdf requests strands; do
  if [ -d "${PYTHON_TARGET}/${mod}" ] || ls "${PYTHON_TARGET}/${mod}"*.py >/dev/null 2>&1; then
    echo "  ok   ${mod}"
  else
    echo "  MANQUE ${mod}" >&2
    exit 1
  fi
done
echo "[layer] prêt. cd iac/control-plane && cdk synth utilisera ce layer."
