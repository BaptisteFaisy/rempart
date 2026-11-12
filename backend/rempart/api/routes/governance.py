"""Routes de gouvernance : dossier de preuves, industrialisation, prévision.

Trois capacités existaient côté backend sans aucune route HTTP — donc invisibles
dans le portail :
- le dossier de preuves d'audit (EF-RAP-04, `reports/evidence.py`) ;
- les métriques d'industrialisation (#68, #26, #47, `reports/industrialization/`) ;
- la prévision de budget (#44, EF-BUD-04, `reports/forecast.py`).

Toutes en lecture seule sauf `POST /evidence`, qui ne fait que régénérer un
document à partir de données déjà stockées : rien n'est modifié dans le store
hors l'enregistrement du rapport produit.
"""

from __future__ import annotations

from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    authorize,
    current_month,
    error_response,
    get_store,
    load_tenant_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.reports.evidence import build_and_upload, build_evidence_pack
from rempart.reports.forecast import forecast_month
from rempart.reports.industrialization import (
    alert_fatigue_indicators,
    analyst_minutes_saved,
    corpus_statistics,
    human_intervention_rate,
)

MAX_PERIOD_LENGTH = 7


def _authorized_tenant(ctx: ApiContext) -> tuple[str, Any] | tuple[None, Any]:
    """Autorisation AVANT toute lecture, puis vérification d'existence."""
    principal, err = require_principal(ctx)
    if err:
        return None, err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=False)
    if err:
        return None, err
    _tenant, err = load_tenant_or_404(get_store(ctx), tenant_id)
    if err:
        return None, err
    return tenant_id, None


def _period(ctx: ApiContext) -> str:
    """Période demandée (`?period=AAAA-MM`) ou mois courant."""
    raw = str(ctx.query.get("period") or ctx.query.get("month") or "").strip()
    if len(raw) == MAX_PERIOD_LENGTH and raw[4] == "-":
        return raw
    return current_month()


def get_evidence(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """`GET /v1/tenants/{id}/evidence` — le dossier de preuves, non scellé."""
    tenant_id, err = _authorized_tenant(ctx)
    if err or not tenant_id:
        return err  # type: ignore[return-value]
    pack = build_evidence_pack(
        store=get_store(ctx), tenant_id=tenant_id, period=_period(ctx)
    )
    return 200, pack


def post_evidence(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """`POST /v1/tenants/{id}/evidence` — génère, scelle (SHA-256) et renvoie.

    Sans bucket configuré (`REMPART_REPORTS_BUCKET`), la route répond **501** :
    annoncer 201 avec une clé S3 alors que rien n'est téléversé ferait croire à
    un auditeur que le dossier est conservé et vérifiable.
    """
    principal, err = require_principal(ctx)
    if err:
        return err
    tenant_id = ctx.path_params.get("id", "")
    err = authorize(principal, tenant_id, write=True)
    if err:
        return err
    store = get_store(ctx)
    _tenant, err = load_tenant_or_404(store, tenant_id)
    if err:
        return err
    if getattr(ctx, "s3", None) is None:
        ctx.audit("evidence.storage_unavailable", "tenant", tenant_id, result="denied")
        return error_response(
            "Stockage des dossiers de preuves non configuré : le dossier ne peut "
            "pas être conservé. Utilisez GET pour le consulter sans scellement "
            "stocké.",
            501,
        )
    period = _period(ctx)
    sealed = build_and_upload(
        store=store,
        tenant_id=tenant_id,
        period=period,
        s3=ctx.s3,
    )
    ctx.audit("evidence.generated", "tenant", tenant_id)
    return 201, sealed


def get_industrialization(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """`GET /v1/tenants/{id}/industrialization` — le service scale-t-il vraiment ?"""
    tenant_id, err = _authorized_tenant(ctx)
    if err or not tenant_id:
        return err  # type: ignore[return-value]
    store = get_store(ctx)
    period = _period(ctx)
    return 200, {
        "tenant_id": tenant_id,
        "period": period,
        "intervention": human_intervention_rate(store, tenant_id=tenant_id, period=period),
        "alert_fatigue": alert_fatigue_indicators(
            store, tenant_id=tenant_id, period=period
        ),
        "minutes_saved": analyst_minutes_saved(store, tenant_id=tenant_id, period=period),
        "corpus": corpus_statistics(store, tenant_id=tenant_id),
    }


def get_forecast(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """`GET /v1/tenants/{id}/forecast` — projection de fin de mois."""
    tenant_id, err = _authorized_tenant(ctx)
    if err or not tenant_id:
        return err  # type: ignore[return-value]
    store = get_store(ctx)
    tenant, _ = load_tenant_or_404(store, tenant_id)
    rate = float(ctx.settings.hourly_rate) if ctx.settings else 50.0
    forecast = forecast_month(
        store,
        tenant_id=tenant_id,
        period=_period(ctx),
        hourly_rate=rate,
    )
    payload = forecast.to_dict()
    payload["tenant_name"] = tenant.name if tenant else tenant_id
    return 200, payload


def register(router: Router) -> None:
    """Routes en lecture seule, sauf la génération du dossier de preuves.

    Aucune route d'écriture n'est exposée sur ces ressources : le dossier de
    preuves et les métriques sont des lectures de l'existant. `POST /evidence`
    régénère un document sans modifier la moindre donnée du store.
    """
    router.add("GET", "/v1/tenants/:id/evidence", get_evidence)
    router.add("POST", "/v1/tenants/:id/evidence", post_evidence)
    router.add("GET", "/v1/tenants/:id/industrialization", get_industrialization)
    router.add("GET", "/v1/tenants/:id/forecast", get_forecast)
