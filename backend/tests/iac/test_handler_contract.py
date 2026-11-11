"""Contract test between the CDK templates and the Python handlers it declares.

Specification: ``CONTRACT-PHASE0.md`` section 5. Every ``Handler`` property of
every ``AWS::Lambda::Function`` produced by the synthesised stacks must name a
module that imports and a function that accepts ``(event, context)``. This is
what makes A1/A2/A3 impossible to reintroduce: a handler invented in the CDK
breaks the CI instead of breaking the first deployment.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any, Callable

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

BACKEND_DIR = Path(__file__).resolve().parents[2]
IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
for _path in (BACKEND_DIR, IAC_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app import build_app  # noqa: E402
from stacks._helpers import split_handler  # noqa: E402

# Handlers the contract names explicitly, whatever the stacks contain.
MANDATORY_HANDLERS = ("rempart.api.app.lambda_handler",)

# Modules the contract forbids as Lambda entrypoints (task signatures are
# ``(payload, deps)``; they must be wrapped by ``lambda_handlers``).
FORBIDDEN_MODULES = (
    "rempart.orchestrator.tasks",
    "rempart.orchestrator.discovery",
)


def synthesized_handlers() -> dict[str, str]:
    """Map every Lambda ``Handler`` of the app to the stack that declares it."""
    app = build_app()
    app.synth()
    handlers: dict[str, str] = {}
    for stack in app.node.children:
        if not isinstance(stack, cdk.Stack):
            continue
        template = assertions.Template.from_stack(stack)
        for resource in template.find_resources("AWS::Lambda::Function").values():
            handler = resource["Properties"]["Handler"]
            handlers[handler] = stack.stack_name
    return handlers


def _import_function(handler: str) -> tuple[Callable[..., Any] | None, str | None]:
    """Import a ``module.function`` handler, returning the problem if any."""
    module_name, function_name = split_handler(handler)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - any import failure is a finding
        return None, f"{handler}: module {module_name!r} non importable ({exc})"
    function = getattr(module, function_name, None)
    if function is None or not callable(function):
        return None, f"{handler}: fonction {function_name!r} absente de {module_name!r}"
    return function, None


def signature_problem(handler: str, function: Callable[..., Any]) -> str | None:
    """Check the handler can be invoked as ``function(event, context)``."""
    try:
        inspect.signature(function).bind(object(), object())
    except TypeError as exc:
        return f"{handler}: signature incompatible avec (event, context) ({exc})"
    return None


def handler_problem(handler: str) -> str | None:
    """Return a human readable problem for one handler, or ``None`` if valid."""
    function, problem = _import_function(handler)
    if problem is not None:
        return problem
    assert function is not None
    return signature_problem(handler, function)


@pytest.fixture(scope="module")
def handlers() -> dict[str, str]:
    """Synthesised handlers, computed once for the whole module."""
    return synthesized_handlers()


def test_synthesized_handlers_are_not_empty(handlers: dict[str, str]) -> None:
    """The extraction must actually see the declared Lambdas."""
    assert len(handlers) >= 10, handlers


@pytest.mark.parametrize("handler", MANDATORY_HANDLERS)
def test_mandatory_handlers_are_declared(handlers: dict[str, str], handler: str) -> None:
    """Handlers named by the contract must appear in a synthesised stack."""
    assert handler in handlers, f"{handler} absent des templates CDK synthétisés"


def test_every_handler_is_importable_with_event_context(
    handlers: dict[str, str],
) -> None:
    """Every declared handler exists in the code with a ``(event, context)`` signature."""
    problems = [p for h in handlers if (p := handler_problem(h)) is not None]
    assert not problems, "Handlers déclarés par le CDK sans implémentation valide:\n" + "\n".join(
        problems
    )


def test_no_handler_points_at_non_lambda_task_modules(
    handlers: dict[str, str],
) -> None:
    """Task functions (``payload, deps``) must never be Lambda entrypoints."""
    offenders = [
        f"{handler} (stack {stack})"
        for handler, stack in handlers.items()
        if split_handler(handler)[0] in FORBIDDEN_MODULES
    ]
    assert not offenders, "Handlers non conformes au contrat:\n" + "\n".join(offenders)
