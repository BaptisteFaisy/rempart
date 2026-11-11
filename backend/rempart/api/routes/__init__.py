"""Route module registry for rempart.api."""

from rempart.api.router import Router

from . import (
    applications,
    budget,
    events,
    findings,
    kpis,
    onboarding,
    reports,
    runs,
    tenants,
)

_ROUTE_MODULES = (
    tenants,
    applications,
    onboarding,
    runs,
    events,
    findings,
    kpis,
    reports,
    budget,
)


def register_all(router: Router) -> None:
    """Register every route module's handlers onto the given router."""
    for module in _ROUTE_MODULES:
        module.register(router)


__all__ = ["register_all"]
