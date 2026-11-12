#!/usr/bin/env bash
# submission_check.sh — vérification one-shot de la démo publique Rempart.
#
# Rejouable par n'importe qui, sans secret, sans compte AWS :
#   bash scripts/submission_check.sh
#
# Contrôles :
#   1. https://tradoooo.github.io/rempart/ répond 200 ;
#   2. les routes profondes (/fleet /evidence /audit /triage) servent le SPA
#      (200, ou 404 avec le HTML du bundle — normal sur GitHub Pages) ;
#   3. le bundle JS téléchargé contient les 5 pages de gouvernance ;
#   4. docs/img/*.png existantes sont listées ;
#   5. imprime le bloc « à coller sur Devpost ».
#
# Code de sortie : 0 si tout est conforme, 1 sinon.

set -uo pipefail

BASE="https://tradoooo.github.io/rempart"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURL_TIMEOUT=30

BUNDLE_STRINGS=(
  "Evidence Dossier"
  "Audit Journal"
  "Industrialization"
  "Forecast"
  "Contract Correction Policy"
)
DEEP_ROUTES=(fleet evidence audit triage)

fail=0

msg()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

# fetch <url> <outfile> -> http_code (000 en cas d'échec réseau)
fetch() {
  local code
  code="$(curl -sS -o "$2" -w '%{http_code}' --max-time "${CURL_TIMEOUT}" "$1" 2>/dev/null)" \
    || code="000"
  printf '%s' "${code:-000}"
}

# is_bundle_html <file> : vrai si le HTML contient le script du bundle SPA
is_bundle_html() {
  grep -q 'src="/rempart/assets/' "$1" && grep -q 'id="root"' "$1"
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

step "1. Page d'accueil"
code="$(fetch "${BASE}/" "$tmp/root.html")"
if [ "$code" = "200" ]; then
  msg "   OK   ${BASE}/ -> 200"
else
  msg "   KO   ${BASE}/ -> ${code} (attendu 200)"
  fail=1
fi

step "2. Routes profondes (SPA sur GitHub Pages)"
for route in "${DEEP_ROUTES[@]}"; do
  code="$(fetch "${BASE}/${route}" "$tmp/route.html")"
  if [ "$code" = "200" ]; then
    msg "   OK   /${route} -> 200"
  elif [ "$code" = "404" ] && is_bundle_html "$tmp/route.html"; then
    msg "   OK   /${route} -> 404 (sert le HTML du bundle : normal sur GitHub Pages)"
  else
    msg "   KO   /${route} -> ${code} (pas le HTML du bundle)"
    fail=1
  fi
done

step "3. Contenu du bundle"
bundle_path="$(grep -oE 'src="/rempart/assets/[^"]+\.js"' "$tmp/root.html" | head -1 | sed -E 's/^src="|"$//g')"
if [ -z "$bundle_path" ]; then
  msg "   KO   impossible de trouver le script du bundle dans index.html"
  fail=1
else
  bundle_url="https://tradoooo.github.io${bundle_path}"
  code="$(fetch "${bundle_url}" "$tmp/bundle.js")"
  if [ "$code" != "200" ]; then
    msg "   KO   téléchargement du bundle -> ${code} (${bundle_url})"
    fail=1
  else
    msg "   OK   bundle téléchargé (${bundle_path}, $(wc -c < "$tmp/bundle.js") octets)"
    for string in "${BUNDLE_STRINGS[@]}"; do
      if grep -qF "$string" "$tmp/bundle.js"; then
        msg "   OK   « ${string} » présent dans le bundle"
      else
        msg "   KO   « ${string} » absent du bundle"
        fail=1
      fi
    done
  fi
fi

step "4. Captures docs/img"
count=0
for png in "$REPO_ROOT"/docs/img/*.png; do
  [ -e "$png" ] || continue
  count=$((count + 1))
  msg "   docs/img/$(basename "$png")"
done
msg "   -> ${count} capture(s) PNG listée(s)."

step "5. Bloc à coller sur Devpost"
cat <<'EOF'
--- DÉBUT bloc Devpost (à copier-coller) ---

Lien du projet : https://tradoooo.github.io/rempart/

Rempart transforme le test d'intrusion annuel en abonnement mensuel piloté par
un MSP : à chaque release, un test d'intrusion continu (AWS Continuum) s'exécute
dans le compte du client et bloque la mise en production d'une faille grave,
jusqu'à ce qu'un re-test prouve sa correction.

Chiffres : 914 tests · 30/30 preuves · 12 défauts corrigés

--- FIN bloc Devpost ---
EOF

step "Résultat"
if [ "$fail" -ne 0 ]; then
  msg "ÉCHEC : un ou plusieurs contrôles ci-dessus ont échoué."
  exit 1
fi
msg "Tous les contrôles sont conformes."
exit 0