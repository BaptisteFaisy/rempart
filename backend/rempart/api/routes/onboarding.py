"""Route handlers for Application Onboarding."""

import uuid
from typing import Any

from rempart.api.context import ApiContext
from rempart.api.helpers import (
    Response,
    authorize,
    error_response,
    get_store,
    load_or_404,
    require_principal,
)
from rempart.api.router import Router
from rempart.common.models import Application, TestConfig

DEFAULT_DOMAIN = "staging.example.com"

# CreateTargetDomain (doc officielle) : verificationMethod est REQUIS et n'a
# que trois valeurs. HTTP_ROUTE ne demande aucun accès DNS — il suffit de
# publier un jeton sur une route de l'application — ce qui évite d'acheter un
# domaine pour une démonstration. DNS_TXT reste le défaut en production.
VERIFICATION_METHODS = ("DNS_TXT", "HTTP_ROUTE", "PRIVATE_VPC")
DEFAULT_VERIFICATION_METHOD = "DNS_TXT"


def _verification_instructions(method: str, domain: str, details: Any) -> dict[str, Any]:
    """Ce que le client doit faire pour prouver la propriété du domaine.

    La réponse de CreateTargetDomain porte `verificationDetails` : soit
    `dnsTxt {dnsRecordName, dnsRecordType, token}`, soit `httpRoute
    {routePath, token}`. On le traduit en consigne actionnable au lieu de
    renvoyer la structure brute.
    """
    details = details if isinstance(details, dict) else {}
    dns = details.get("dnsTxt") or {}
    http = details.get("httpRoute") or {}
    if method == "HTTP_ROUTE" and http:
        return {
            "method": method,
            "domain": domain,
            "action": (
                f"Publier le jeton « {http.get('token', '')} » sur la route "
                f"{http.get('routePath', '/')} de https://{domain}"
            ),
            "requires_dns_access": False,
            "details": http,
        }
    if dns:
        return {
            "method": method,
            "domain": domain,
            "action": (
                f"Créer l'enregistrement {dns.get('dnsRecordType', 'TXT')} "
                f"{dns.get('dnsRecordName', '_awscontinuum')} avec la valeur "
                f"« {dns.get('token', '')} »"
            ),
            "requires_dns_access": True,
            "details": dns,
        }
    return {
        "method": method,
        "domain": domain,
        "action": "Aucune instruction renvoyée par le service",
        "requires_dns_access": method != "HTTP_ROUTE",
        "details": details,
    }


def _load_app_or_404(ctx: ApiContext, app_id: str) -> tuple[Application | None, Response | None]:
    return load_or_404(get_store(ctx).get_application, app_id, "Application")

def _setup_domains(
    sa: Any, domains: list[str], method: str
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Create and verify each target domain.

    Rendre ``(targetDomainIds, noms, instructions)``. CreateTargetDomain exige
    ``targetDomainName`` + ``verificationMethod`` et répond avec
    ``targetDomainId`` et ``verificationDetails`` ; VerifyTargetDomain exige
    ``targetDomainId``.
    """
    domain_ids: list[str] = []
    verified: list[str] = []
    instructions: list[dict[str, Any]] = []
    for domain in domains:
        dom_resp = sa.create_target_domain(domain, verification_method=method)
        domain_id = dom_resp.get("targetDomainId", "")
        sa.verify_target_domain(domain_id)
        domain_ids.append(domain_id)
        verified.append(dom_resp.get("domainName") or domain)
        instructions.append(
            _verification_instructions(method, domain, dom_resp.get("verificationDetails"))
        )
    return domain_ids, verified, instructions

def _provision_space(
    sa: Any, app: Application, method: str
) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Create the target domains then the agent space.

    L'association espace/domaines passe par ``targetDomainIds`` (CreateAgentSpace),
    CreateTargetDomain ne prenant pas d'``agentSpaceId``.
    """
    domain_ids, domains, instructions = _setup_domains(
        sa, app.domains or [DEFAULT_DOMAIN], method
    )
    space = sa.create_agent_space(f"space-{app.name}", targetDomainIds=domain_ids)
    space_id = space.get("agentSpaceId") or space.get("spaceId")
    return space_id, domains, instructions

def _build_config(app_id: str, sa_pentest_id: str, domains: list[str]) -> TestConfig:
    """Build the default delivery TestConfig for a freshly onboarded app."""
    return TestConfig(
        config_id=f"cfg-{uuid.uuid4().hex[:8]}",
        app_id=app_id,
        sa_pentest_id=sa_pentest_id,
        kind="delivery",
        scope={"domains": domains, "paths": ["/"]},
        risk_types=["IDOR", "SQLi", "BrokenAuth"],
        blocking_threshold="High",
        schedule="0 2 * * *",
    )

def _onboard(
    ctx: ApiContext, app: Application, app_id: str, method: str
) -> tuple[int, dict[str, Any]]:
    """Run the Security Agent onboarding and persist space, app, and config."""
    store = get_store(ctx)
    space_id, verified_domains, instructions = _provision_space(ctx.sa, app, method)

    # CreatePentest exige ``agentSpaceId`` + ``title`` ; réponse : ``pentestId``.
    pentest = ctx.sa.create_pentest(space_id, f"delivery-{app.name}")
    sa_pentest_id = pentest.get("pentestId", f"pt-{uuid.uuid4().hex[:8]}")

    app.agent_space_id = space_id
    if not app.domains:
        app.domains = verified_domains
    store.save_application(app)

    cfg = _build_config(app_id, sa_pentest_id, verified_domains)
    store.save_config(cfg)
    ctx.audit("application.onboarding", "application", app.app_id)

    return 201, {
        "status": "completed",
        "agent_space_id": space_id,
        "domains": verified_domains,
        "config_id": cfg.config_id,
        "sa_pentest_id": sa_pentest_id,
        "verification_method": method,
        "verification_instructions": instructions,
    }

def post_onboarding(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Initialize AgentSpace, TargetDomain, and default TestConfig via Security Agent."""
    principal, err = require_principal(ctx)
    if err:
        return err
    app_id = ctx.path_params.get("id", "")
    app, err = _load_app_or_404(ctx, app_id)
    if err or not app:
        return err  # type: ignore[return-value]

    err = authorize(principal, app.tenant_id, write=True)
    if err:
        return err
    if not ctx.sa:
        return error_response("Security Agent client not available", 500)

    method = str(
        ctx.body.get("verification_method") or DEFAULT_VERIFICATION_METHOD
    ).upper()
    if method not in VERIFICATION_METHODS:
        return error_response(
            f"verification_method invalide : {method}. "
            f"Valeurs acceptées : {', '.join(VERIFICATION_METHODS)}",
            400,
        )
    return _onboard(ctx, app, app_id, method)

def get_onboarding_status(ctx: ApiContext) -> tuple[int, dict[str, Any]]:
    """Get the current onboarding state and agent space for an application."""
    principal, err = require_principal(ctx)
    if err:
        return err
    app_id = ctx.path_params.get("id", "")
    app, err = _load_app_or_404(ctx, app_id)
    if err or not app:
        return err  # type: ignore[return-value]

    err = authorize(principal, app.tenant_id, write=False)
    if err:
        return err

    configs = get_store(ctx).list_configs(app_id)
    return 200, {
        "app_id": app_id,
        "onboarded": bool(app.agent_space_id and len(configs) > 0),
        "agent_space_id": app.agent_space_id,
        "domains": app.domains,
        "configs": [c.to_item() for c in configs],
    }

def register(router: Router) -> None:
    router.add("POST", "/v1/applications/:id/onboarding", post_onboarding)
    router.add("GET", "/v1/applications/:id/onboarding", get_onboarding_status)
