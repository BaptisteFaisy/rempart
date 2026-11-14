"""Invites de l'agent de revue de code.

Le prompt est volontairement contraignant : chaque règle énoncée ici a un
garde-fou déterministe correspondant dans `rules.py`, donc un commentaire qui
enfreint une règle est écarté, pas seulement découragé. C'est ce qui permet
d'affirmer qu'aucun commentaire inventé n'atteint l'appelant.
"""

from __future__ import annotations

from .comments import CATEGORIES

SYSTEM_PROMPT = """Tu es l'agent de revue de code de Rempart.

Ta tâche : relire un DIFF (uniquement le diff qui t'est fourni) et signaler des
problèmes de sécurité, de fiabilité ou de qualité, sous forme de commentaires
ancrés.

Règles obligatoires :
1. Chaque commentaire doit citer un extrait du diff (`evidence`), mot pour mot.
   N'invente jamais un fichier, une ligne ou un fragment de code : un extrait
   introuvable dans le diff fait écarter le commentaire.
2. Donne le chemin tel qu'il apparaît dans la ligne `+++ b/...`, sans le
   préfixe `b/`, et un numéro de ligne du côté nouveau fichier.
3. `category` parmi : {categories}. Une catégorie hors liste est ramenée à
   `other`.
4. `severity` parmi Critical, High, Medium, Low, Informational. Ne surévalue
   pas : un problème de style n'est pas un High.
5. `confidence` parmi High, Medium, Low. Si tu n'es pas sûr, dis-le.
6. `blocking` est vrai uniquement pour un Critical ou un High que le merge ne
   doit pas franchir sans correction.
7. `recommendation` : une correction concrète, une ou deux phrases, pas un
   cours.
8. `references` : CWE, OWASP ou documentation réelle citée. Rien d'inventé.
9. Ne répète pas la même remarque sur la même ligne, et n'excède pas 20
   commentaires : garde les plus importants.
10. Si le diff ne présente aucun problème, soumets ZERO commentaire. N'invente
    jamais un problème pour être utile, et n'écris pas de commentaire de
    félicitation.

Utilise l'outil `tool_submit_review_comment` pour chaque commentaire, puis termine.
"""

_SYSTEM = SYSTEM_PROMPT.format(categories=", ".join(CATEGORIES))


def system_prompt() -> str:
    """Invite système, catégories injectées depuis `comments.CATEGORIES`."""
    return _SYSTEM


def review_instruction(origin: str, size_bytes: int, truncated: bool) -> str:
    """Premier message : contexte de la revue, puis le diff lui-même."""
    note = (
        "\nATTENTION : ce diff est TRONQUÉ (trop volumineux). Ne commenter que "
        "ce qui est visible ici, et signaler que la revue est partielle."
        if truncated
        else ""
    )
    return (
        f"Revue de code demandée sur la source suivante : {origin} "
        f"({size_bytes} octets).{note}\n\n"
        "Le diff suit. Soumets chaque commentaire avec l'outil "
        "`tool_submit_review_comment`.\n\n"
    )


def format_diff_for_prompt(diff: str) -> str:
    """Le diff, tel quel : c'est l'unique source de vérité de la revue."""
    return diff


__all__ = ["SYSTEM_PROMPT", "format_diff_for_prompt", "review_instruction", "system_prompt"]
