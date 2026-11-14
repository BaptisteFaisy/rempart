"""Route module registry for rempart.api."""

from rempart.api.router import Router

from . import (
    applications,
    audit,
    budget,
    events,
    findings,
    github_webhook,
    governance,
    kpis,
    onboarding,
    reports,
    reviews,
    runs,
    settings,
    tenants,
)

_ROUTE_MODULES = (
    governance,
    tenants,
    applications,
    onboarding,
    runs,
    events,
    github_webhook,
    findings,
    reviews,
    kpis,
    reports,
    budget,
    audit,
    settings,
)


def register_all(router: Router) -> None:
    """Register every route module's handlers onto the given router."""
    for module in _ROUTE_MODULES:
        module.register(router)


__all__ = ["register_all"]
