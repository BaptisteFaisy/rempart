"""Route module registry for rempart.api."""

from rempart.api.router import Router

from . import (
    applications,
    audit,
    budget,
    events,
    findings,
    governance,
    kpis,
    onboarding,
    reports,
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
    findings,
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
