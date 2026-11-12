"""Les trois modes d'identité SES de la stack de notifications.

Raison d'être : l'ancienne version codait en dur `rempart.example.com`, un
domaine que personne ne possède. L'identité restait `PENDING` pour toujours et
la condition IAM `ses:FromAddress` bloquait tout envoi — silencieusement.

Le mode 1 (une adresse) est celui qui coûte **0 €** : le sandbox SES vérifie une
adresse par un simple clic sur l'e-mail reçu, aucune zone DNS à acheter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
if str(IAC_DIR) not in sys.path:
    sys.path.insert(0, str(IAC_DIR))

from stacks.notifications import (  # noqa: E402
    CONFIGURATION_SET_NAME,
    NotificationsStack,
    resolve_from_address,
)

ENV = {"account": "123456789012", "region": "eu-north-1"}


def _template(**kwargs) -> assertions.Template:
    app = cdk.App()
    stack = NotificationsStack(app, "Notif", env=cdk.Environment(**ENV), **kwargs)
    return assertions.Template.from_stack(stack)


def _lambda_props(template: assertions.Template) -> dict:
    functions = template.find_resources("AWS::Lambda::Function")
    assert len(functions) == 1
    return next(iter(functions.values()))["Properties"]


# --------------------------------------------------------------------------- #
# Résolution de l'adresse
# --------------------------------------------------------------------------- #
def test_resolve_prefers_an_exact_address_over_a_domain():
    assert resolve_from_address("ops@msp.example", "msp.example") == "ops@msp.example"


def test_resolve_falls_back_to_noreply_at_domain():
    assert resolve_from_address(None, "msp.example") == "noreply@msp.example"


def test_resolve_without_identity_is_none():
    assert resolve_from_address(None, None) is None


# --------------------------------------------------------------------------- #
# Mode 1 — adresse exacte (sandbox SES, 0 €)
# --------------------------------------------------------------------------- #
def test_email_mode_creates_an_email_identity():
    template = _template(from_email="ops@msp.example")
    template.resource_count_is("AWS::SES::EmailIdentity", 1)
    template.has_resource_properties(
        "AWS::SES::EmailIdentity", {"EmailIdentity": "ops@msp.example"}
    )


def test_email_mode_pins_the_iam_condition_to_that_address():
    """La permission d'envoi doit rester bornée à l'adresse déclarée."""
    template = _template(from_email="ops@msp.example")
    policies = template.find_resources("AWS::IAM::Policy")
    conditions = [
        statement.get("Condition", {})
        for policy in policies.values()
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
        if "ses:SendEmail" in statement.get("Action", [])
    ]
    assert conditions, "aucune permission ses:SendEmail trouvée"
    assert conditions[0] == {"StringEquals": {"ses:FromAddress": "ops@msp.example"}}


def test_email_mode_exports_the_address_to_the_lambda():
    props = _lambda_props(_template(from_email="ops@msp.example"))
    env = props["Environment"]["Variables"]
    assert env["REMPART_SES_FROM_ADDRESS"] == "ops@msp.example"
    # Le nom du configuration set est un jeton CloudFormation (résolu au
    # déploiement), pas une chaîne littérale : on vérifie la référence.
    assert "Ref" in env["REMPART_SES_CONFIGURATION_SET"]
    # Le domaine ne doit PAS être exporté en même temps : l'adresse prime.
    assert "REMPART_SES_FROM_DOMAIN" not in env


# --------------------------------------------------------------------------- #
# Mode 2 — domaine (production, zone DNS requise)
# --------------------------------------------------------------------------- #
def test_domain_mode_creates_a_domain_identity():
    template = _template(from_domain="msp.example")
    template.resource_count_is("AWS::SES::EmailIdentity", 1)
    template.has_resource_properties(
        "AWS::SES::EmailIdentity", {"EmailIdentity": "msp.example"}
    )


def test_domain_mode_derives_noreply_address():
    env = _lambda_props(_template(from_domain="msp.example"))["Environment"]["Variables"]
    assert env["REMPART_SES_FROM_ADDRESS"] == "noreply@msp.example"


# --------------------------------------------------------------------------- #
# Mode 3 — aucune identité (déploiement de l'infrastructure seule)
# --------------------------------------------------------------------------- #
def test_no_identity_still_deploys_the_stack():
    """On peut déployer l'infrastructure avant d'avoir choisi l'adresse."""
    template = _template()
    template.resource_count_is("AWS::SES::EmailIdentity", 0)
    template.resource_count_is("AWS::SES::ConfigurationSet", 1)
    template.resource_count_is("AWS::Lambda::Function", 1)


def test_no_identity_does_not_add_an_empty_iam_condition():
    """Une condition `ses:FromAddress` vide interdirait tout envoi en silence."""
    template = _template()
    policies = template.find_resources("AWS::IAM::Policy")
    for policy in policies.values():
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
            if "ses:SendEmail" in statement.get("Action", []):
                condition = statement.get("Condition", {})
                assert condition in ({}, None), (
                    f"condition IAM vide mais présente : {condition}"
                )


def test_no_identity_exports_no_from_address():
    env = _lambda_props(_template())["Environment"]["Variables"]
    assert "REMPART_SES_FROM_ADDRESS" not in env
    assert "REMPART_SES_FROM_DOMAIN" not in env


# --------------------------------------------------------------------------- #
# Garde-fous transverses
# --------------------------------------------------------------------------- #
def test_tls_is_required_on_the_configuration_set():
    """Les e-mails contiennent des échéances et des liens : TLS obligatoire."""
    template = _template()
    template.has_resource_properties(
        "AWS::SES::ConfigurationSet",
        {
            "Name": CONFIGURATION_SET_NAME,
            "DeliveryOptions": {"TlsPolicy": "REQUIRE"},
        },
    )


def test_handler_points_at_the_real_notification_module():
    """Anti-récidive du placeholder : le handler doit exister pour de vrai."""
    props = _lambda_props(_template())
    assert props["Handler"] == "rempart.notifications.handler.lambda_handler"

    module_name, function_name = props["Handler"].rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_name)
    assert callable(getattr(module, function_name, None))


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"from_email": "a@b.c"}, "a@b.c"),
        ({"from_domain": "b.c"}, "noreply@b.c"),
        ({}, None),
    ],
)
def test_stack_exposes_the_effective_address(kwargs, expected):
    app = cdk.App()
    stack = NotificationsStack(app, "Notif", env=cdk.Environment(**ENV), **kwargs)
    assert stack.from_address == expected


def test_outputs_announce_the_sending_address():
    """Un opérateur doit voir l'adresse effective sans lire le template."""
    outputs = _template(from_email="ops@msp.example").to_json()["Outputs"]
    values = [v.get("Value") for v in outputs.values()]
    assert "ops@msp.example" in values
