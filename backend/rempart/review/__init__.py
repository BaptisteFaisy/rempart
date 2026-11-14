"""Revue de code par agent InferHub (EF-ONB-04).

Ce paquet est indépendant de Continuum : la fonction « code review » d'AWS
Security Agent est payante (200 $/M lignes/mois + 10 $/inférence) et hors essai
gratuit, donc Rempart ne l'appelle pas. La revue est faite par le même agent
InferHub que le triage, avec des garde-fous déterministes.
"""

from .agent import (
    STATUS_MODEL_UNAVAILABLE,
    STATUS_PARTIAL,
    STATUS_REVIEWED,
    ReviewContext,
    ReviewResult,
    run_review,
)
from .comments import CATEGORIES, ReviewComment
from .diff import DiffSource, from_commit, from_pull, from_text, split_repository
from .rules import MAX_COMMENTS, enforce

__all__ = [
    "CATEGORIES",
    "MAX_COMMENTS",
    "DiffSource",
    "ReviewComment",
    "ReviewContext",
    "ReviewResult",
    "STATUS_MODEL_UNAVAILABLE",
    "STATUS_PARTIAL",
    "STATUS_REVIEWED",
    "enforce",
    "from_commit",
    "from_pull",
    "from_text",
    "run_review",
    "split_repository",
]
