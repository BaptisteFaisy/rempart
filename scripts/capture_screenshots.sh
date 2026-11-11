#!/usr/bin/env bash
# Capture les écrans du portail Rempart pour la documentation (idée #42).
#
# Le dépôt n'avait aucune image : les juges lisent le README avant de regarder
# la vidéo. Ces captures sont prises sur la DÉMO LOCALE (jeu de données figé),
# donc elles sont reproductibles par n'importe qui, sans compte AWS et sans
# qu'un dollar soit dépensé.
#
# Prérequis : google-chrome (headless), node, et le venv backend.
#
# Usage :
#   ./scripts/capture_screenshots.sh
#   ./scripts/capture_screenshots.sh --api-port 8791 --web-port 5173
#
# Sortie : docs/img/*.png (une par page du portail).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/img"
API_PORT=8791
WEB_PORT=5173
PYTHON="${REPO_ROOT}/.venv/bin/python"
CHROME="${CHROME:-google-chrome}"
BASE_URL=""

log() { echo "[capture] $*"; }

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --api-port) API_PORT="$2"; shift 2 ;;
      --web-port) WEB_PORT="$2"; shift 2 ;;
      *) echo "option inconnue : $1" >&2; exit 2 ;;
    esac
  done
}

check_prereqs() {
  [ -x "${PYTHON}" ] || { echo "venv absent : ${PYTHON}" >&2; exit 1; }
  command -v "${CHROME}" >/dev/null 2>&1 || {
    echo "chrome absent (CHROME=... pour pointer un autre binaire)" >&2; exit 1; }
  [ -d "${REPO_ROOT}/portal/node_modules" ] || {
    echo "dépendances du portail absentes : cd portal && npm ci" >&2; exit 1; }
}

start_api() {
  log "API locale sur le port ${API_PORT}"
  (cd "${REPO_ROOT}" && nohup "${PYTHON}" scripts/serve_local.py --port "${API_PORT}" \
    > /tmp/rempart-capture-api.log 2>&1 &)
  wait_for "http://127.0.0.1:${API_PORT}/v1/tenants" "l'API locale"
}

start_web() {
  log "portail Vite sur le port ${WEB_PORT}"
  (cd "${REPO_ROOT}/portal" && VITE_API_URL="http://127.0.0.1:${API_PORT}" \
    VITE_DEMO_ROLE=platform_admin VITE_DEMO_TENANT=demo-a \
    nohup npx vite --port "${WEB_PORT}" --strictPort > /tmp/rempart-capture-vite.log 2>&1 &)
  wait_for "http://127.0.0.1:${WEB_PORT}/" "le portail"
}

wait_for() {
  local url="$1" label="$2" tries=30
  while [ "${tries}" -gt 0 ]; do
    if curl -sS -o /dev/null --max-time 2 "${url}" 2>/dev/null; then return 0; fi
    tries=$((tries - 1)); sleep 1
  done
  echo "${label} ne répond pas sur ${url}" >&2; exit 1
}

stop_all() {
  pkill -f "serve_local.py --port ${API_PORT}" 2>/dev/null || true
  pkill -f "vite --port ${WEB_PORT}" 2>/dev/null || true
}

shoot() {
  local name="$1" path="$2" out="${OUT_DIR}/$1.png"
  "${CHROME}" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --force-device-scale-factor=1 --window-size=1440,1000 \
    --virtual-time-budget=9000 --timeout=25000 \
    --screenshot="${out}" "${BASE_URL}${path}" >/dev/null 2>&1 || true
  if [ -s "${out}" ]; then
    log "OK ${name}.png ($(du -h "${out}" | cut -f1))"
  else
    echo "capture échouée : ${name}" >&2; return 1
  fi
}

shoot_all() {
  mkdir -p "${OUT_DIR}"
  shoot "01-fleet" "/fleet"
  shoot "02-tenant" "/tenants/demo-a"
  shoot "03-application" "/applications/app-shop"
  shoot "04-run" "/runs/run-app-shop-1"
  shoot "05-finding" "/findings/f-app-shop-0"
  shoot "06-triage" "/triage"
  shoot "07-budget" "/budget"
  shoot "08-reports" "/reports"
  shoot "09-login" "/login"
}

main() {
  parse_args "$@"
  check_prereqs
  BASE_URL="http://127.0.0.1:${WEB_PORT}"
  # Le trap s'occupe de l'arrêt, y compris si une capture échoue en route.
  trap stop_all EXIT
  start_api
  start_web
  shoot_all
  log "terminé : ${OUT_DIR}"
}

main "$@"
