#!/usr/bin/env python3
"""Porte de validation de l'agent de conflit (projet Rempart).

Une résolution de conflit **ne doit jamais atteindre la branche sans passer les
gardes du dépôt**. Leçon mesurée sur sam-vision (PR #615) : une réconciliation
avait poussé une tête cassée, le balayeur avait classé l'échec « réel », et la
PR était morte en silence jusqu'à une reprise humaine.

Ici, avant le push : `py_compile` sur les modules touchés, puis — selon la zone
modifiée — `pytest` + `ruff` sur le backend, `pytest` sur les apps de démo,
`vitest run` sur le portail. Rouge → rien n'est poussé, la branche reste
intacte, la PR reste `DIRTY` (le tour suivant rappelle l'agent, dans la limite
du quota) et le compte rendu cite les erreurs.

Une porte qui ne peut pas s'exécuter (outil absent, délai dépassé) ne bloque
rien et le dit : le bail de la CI reste la preuve. Coupe-circuit :
`CONFLICT_COMPILE_GATE=0`.

Bibliothèque standard uniquement, aucune horloge implicite, aucun secret.
"""

import os
import subprocess
import sys

GATE_ENV = "CONFLICT_COMPILE_GATE"
GATE_TIMEOUT_S = 240
GATE_EXCERPT = 1_500
# Marqueur de la tête posée par l'agent : le balayeur le cherche mot pour mot
# pour attribuer un échec à la résolution (label `intervention-humaine`) au
# lieu de laisser la PR mourir en silence.
MARK_AGENT = "<!-- agent-conflit sha=%s -->"
VENV_PYTHON = os.path.join(".venv", "bin", "python")


def _log(message):
    print("inferhub-agent: %s" % message, flush=True)


def fichiers_modifies(base="origin/main"):
    """Fichiers que la branche change par rapport à `base` (best-effort)."""
    try:
        proc = subprocess.run(["git", "diff", "--name-only", "%s...HEAD" % base],
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        _log("diff illisible, rien à vérifier : %s" % exc)
        return []
    if proc.returncode != 0:
        _log("diff illisible (%s), rien à vérifier" % base)
        return []
    return [line for line in (proc.stdout or "").splitlines() if line.strip()]


def portees(fichiers):
    """(fichiers Python, zones touchées) pour ces chemins.

    Les zones pilotent les suites à rejouer : `backend`, `demo`, `portal`.
    Tout le reste (docs, IaC, JSON) ne prouve rien par un test unitaire et
    n'est vérifié que par `py_compile` quand c'est du Python.
    """
    python, zones = [], set()
    for path in fichiers:
        if path.endswith(".py"):
            python.append(path)
        for zone in ("backend", "demo", "portal"):
            if path.startswith(zone + "/"):
                zones.add(zone)
    return python, zones


def interpreteur():
    """Python du dépôt si un venv est présent, sinon l'interpréteur courant."""
    return VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable


def lance(commande, cwd=None, timeout=GATE_TIMEOUT_S):
    """Exécute une commande et rend (code, sortie). 0 si non exécutable."""
    try:
        proc = subprocess.run(commande, capture_output=True, text=True,
                              cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "délai de %d s dépassé" % timeout
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "non exécutable : %s" % exc
    return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")


def extrait(etape, texte):
    """Extrait publiable : les lignes d'erreur, sinon la fin du journal."""
    lignes = [ligne.strip() for ligne in texte.splitlines() if ligne.strip()]
    fautes = [ligne for ligne in lignes
              if ligne.startswith("FAILED") or ligne.startswith("ERROR")
              or "error:" in ligne or ligne.startswith("E  ")
              or "Error:" in ligne]
    garde = fautes[:8] or lignes[-8:]
    return "`%s` :\n```\n%s\n```" % (etape, "\n".join(garde)[:GATE_EXCERPT])


def verifier_python(paths):
    """`py_compile` sur chaque module touché. Rend (ok, message)."""
    for path in paths:
        code, texte = lance([interpreteur(), "-m", "py_compile", path], timeout=60)
        if code is None:
            return True, "porte sautée (py_compile) : %s" % texte
        if code != 0:
            return False, extrait("py_compile %s" % path, texte)
    return True, "py_compile OK (%d fichier(s))" % len(paths)


def verifier_backend():
    """pytest + ruff du backend. Rend (ok, message)."""
    py = interpreteur()
    code, texte = lance([py, "-m", "pytest", "tests", "-q"], cwd="backend")
    if code is None:
        return True, "porte backend sautée : %s" % texte
    if code != 0:
        return False, extrait("pytest backend", texte)
    ruff = os.path.join(".venv", "bin", "ruff")
    commande = [ruff] if os.path.exists(ruff) else [py, "-m", "ruff"]
    code, texte = lance(commande + ["check", "rempart", "tests"], cwd="backend")
    if code is None:
        return True, "pytest backend OK (ruff sauté : %s)" % texte
    if code != 0:
        return False, extrait("ruff backend", texte)
    return True, "pytest + ruff backend OK"


def verifier_demo():
    """pytest des applications de démonstration. Rend (ok, message)."""
    code, texte = lance([interpreteur(), "-m", "pytest", "demo", "-q"])
    if code is None:
        return True, "porte démo sautée : %s" % texte
    if code != 0:
        return False, extrait("pytest demo", texte)
    return True, "pytest demo OK"


def verifier_portal():
    """vitest du portail (build laissé à la CI : trop long ici). (ok, message)."""
    if not os.path.isdir(os.path.join("portal", "node_modules")):
        return True, "porte portail sautée : dépendances non installées"
    code, texte = lance(["npx", "--no-install", "vitest", "run"], cwd="portal")
    if code is None:
        return True, "porte portail sautée : %s" % texte
    if code != 0:
        return False, extrait("vitest portal", texte)
    return True, "vitest portail OK"


SUITES = {"backend": verifier_backend, "demo": verifier_demo, "portal": verifier_portal}


def verifier_compilation(fichiers=None):
    """Vérifie les gardes des zones touchées avant le push. Rend (ok, message).

    `ok` faux n'est pas une panne : c'est la preuve que la résolution est
    cassée, donc le push est refusé et la branche reste intacte.
    """
    if os.environ.get(GATE_ENV, "1") == "0":
        return True, "porte désactivée (%s=0)" % GATE_ENV
    if not os.path.isdir("backend"):
        return True, "porte sautée : dépôt Rempart non reconnu ici"
    fichiers = fichiers_modifies() if fichiers is None else fichiers
    python, zones = portees(fichiers)
    if python:
        ok, message = verifier_python(python)
        if not ok:
            return False, message
    else:
        message = "aucun module Python touché"
    if not zones:
        return True, "porte : %s, aucune zone testable" % message
    for zone in sorted(zones):
        ok, suite = SUITES[zone]()
        if not ok:
            return False, suite
        message = "%s ; %s" % (message, suite)
    return True, message


def tete_git():
    """SHA de la tête (le push ne la change pas : marqueur exact)."""
    code, texte = lance(["git", "rev-parse", "HEAD"], timeout=60)
    return texte.strip() if code == 0 else ""


def prepare_push(files, branch, fichiers=None):
    """(ok, message, corps) : décide du push et prépare son compte rendu.

    Le corps porte le marqueur de tête en première ligne ; l'appelant ne le
    poste qu'après un push réussi.
    """
    ok, message = verifier_compilation(fichiers)
    if not ok:
        return False, message, ""
    unique = sorted(set(files))
    corps = ("%s\n\nConflit réconcilié par l'agent : %d fichier(s) (%s), "
             "rebase poussé sur `%s` (%s). La file reprend."
             % (MARK_AGENT % tete_git(), len(unique), ", ".join(unique),
                branch, message))
    return True, message, corps
