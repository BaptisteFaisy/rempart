"""Garde-fous de la revue de code : rien de ce que dit le modèle n'est cru.

Un commentaire doit être ancré dans le diff **réel** : fichier présent, ligne du
côté nouveau, extrait citable mot pour mot. Sans cela, la revue produirait des
constats sur du code qui n'existe pas — et le compteur affiché au juge serait
faux. Ces tests verrouillent chaque règle d'écartement, plus le tri sous plafond.
"""

from __future__ import annotations

from rempart.review.comments import ReviewComment
from rempart.review.rules import MAX_COMMENTS, enforce, index_diff
from tests.review.conftest import (
    SAMPLE_DIFF,
    SAMPLE_FILE,
    SAMPLE_LINES,
    SECRET_EVIDENCE,
    SQL_EVIDENCE,
    comment_payload,
)


def _comments(*payloads: dict) -> list[ReviewComment]:
    return [ReviewComment.from_dict(p) for p in payloads]


def test_index_diff_retient_le_fichier_et_les_lignes_du_cote_nouveau():
    index = index_diff(SAMPLE_DIFF)
    assert index.has_file(SAMPLE_FILE)
    assert all(index.has_line(SAMPLE_FILE, line) for line in SAMPLE_LINES)
    # Une ligne hors hunk n'existe pas pour la revue.
    assert not index.has_line(SAMPLE_FILE, 999)
    assert not index.has_file("api/autre.py")


def test_commentaire_ancre_est_conserve():
    out = enforce(_comments(comment_payload()), SAMPLE_DIFF)
    assert len(out.comments) == 1
    assert out.dropped == []
    assert out.comments[0].evidence == SECRET_EVIDENCE


def test_fichier_invente_ecarte():
    out = enforce(_comments(comment_payload(file="api/fantome.py")), SAMPLE_DIFF)
    assert out.comments == []
    assert "absent du diff" in out.dropped[0]["reason"]


def test_ligne_inventee_ecarree():
    out = enforce(_comments(comment_payload(line=4242)), SAMPLE_DIFF)
    assert out.comments == []
    assert "absente du diff" in out.dropped[0]["reason"]


def test_extrait_invente_ecarte():
    """Le cas grave : un modèle qui cite du code absent du diff doit être écarté."""
    out = enforce(_comments(comment_payload(evidence='api_key = "sk-live-INVENTEE"')), SAMPLE_DIFF)
    assert out.comments == []
    assert "citation inventée" in out.dropped[0]["reason"]


def test_extrait_cite_avec_un_espacement_different_est_quand_meme_ancre():
    """La normalisation porte sur les blancs, pas sur le sens : sinon tout est faux positif."""
    spaced = 'api_key   =    "sk-live-abcdef1234567890"'
    out = enforce(_comments(comment_payload(evidence=spaced)), SAMPLE_DIFF)
    assert len(out.comments) == 1


def test_sans_extrait_le_commentaire_est_ecarte():
    out = enforce(_comments(comment_payload(evidence="")), SAMPLE_DIFF)
    assert out.comments == []
    assert "extrait" in out.dropped[0]["reason"]


def test_doublon_fusionne():
    out = enforce(
        _comments(comment_payload(), comment_payload(title="Deuxième formulation")), SAMPLE_DIFF
    )
    assert len(out.comments) == 1
    assert out.dropped[0]["reason"] == "doublon"


def test_categorie_inventee_ramenee_a_other():
    out = enforce(_comments(comment_payload(category="magie")), SAMPLE_DIFF)
    assert out.comments[0].category == "other"


def test_severite_en_majuscules_normalisee_sans_surevaluation():
    out = enforce(_comments(comment_payload(severity="HIGH")), SAMPLE_DIFF)
    assert out.comments[0].severity == "High"
    out2 = enforce(_comments(comment_payload(severity="peu-importante")), SAMPLE_DIFF)
    assert out2.comments[0].severity == "Medium"


def test_bolleen_chaine_false_est_vraiment_faux():
    """`bool("false")` vaut True en Python : le piège mesuré sur le triage, ici aussi."""
    out = enforce(_comments(comment_payload(blocking="false")), SAMPLE_DIFF)
    assert out.comments[0].blocking is False


def test_le_plafond_garde_les_plus_severes():
    """Un plafond ne doit jamais éjecter un Critical au profit d'un Low."""
    payloads = [comment_payload(line=12, severity="Low", evidence=SQL_EVIDENCE, title="bas")]
    payloads += [
        comment_payload(line=line, severity="Critical", title=f"c{line}") for line in (9, 10, 11)
    ]
    out = enforce(_comments(*payloads), SAMPLE_DIFF, limit=2)
    assert len(out.comments) == 2
    assert {c.severity for c in out.comments} == {"Critical"}
    assert any("plafond" in d["reason"] for d in out.dropped)


def test_sans_plafond_explicite_le_defaut_est_celui_du_module():
    out = enforce([], SAMPLE_DIFF)
    assert MAX_COMMENTS == 20
    assert out.comments == []


def test_les_severites_hautes_exigent_un_humain():
    out = enforce(
        _comments(
            comment_payload(),
            comment_payload(line=11, evidence=SQL_EVIDENCE, severity="Low", title="bas"),
        ),
        SAMPLE_DIFF,
    )
    assert out.needs_human == [f"{SAMPLE_FILE}:10"]
