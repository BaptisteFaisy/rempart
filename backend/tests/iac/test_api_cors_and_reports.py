"""Garde-fous IaC : preflight CORS, origines restreintes, bucket des preuves.

Ces tests verrouillent trois constats réels du 2026-11-12 sur l'environnement
déployé (eu-north-1, compte 710332178565) :

1. le preflight `OPTIONS /v1/tenants` répondait **401** (la route
   `ANY /v1/{proxy+}` porte l'autorisateur JWT, et ANY comprend OPTIONS) → aucun
   appel cross-origin du portail CloudFront n'aboutissait ;
2. l'API répondait `Access-Control-Allow-Origin: *` sur toutes ses réponses ;
3. aucun bucket de rapports n'existait dans le compte, alors que
   `POST /v1/tenants/{id}/evidence` répondait 201 avec une clé S3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aws_cdk import assertions

IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
if str(IAC_DIR) not in sys.path:
    sys.path.insert(0, str(IAC_DIR))

from app import build_app  # noqa: E402

PORTAL_ORIGIN = "https://d1o2xnfrq8xomh.cloudfront.net"


def _template(stack_name: str) -> assertions.Template:
    app = build_app()
    app.synth()
    return assertions.Template.from_stack(app.node.find_child(stack_name))


def _routes(template: assertions.Template) -> dict[str, dict]:
    found = template.find_resources("AWS::ApiGatewayV2::Route")
    return {props["Properties"]["RouteKey"]: props["Properties"] for props in found.values()}


def test_preflight_options_route_exists_without_authorizer():
    """OPTIONS ne doit JAMAIS porter l'autorisateur JWT, sinon 401 au preflight."""
    routes = _routes(_template("RempartApiStack"))
    assert "OPTIONS /v1/{proxy+}" in routes, sorted(routes)
    assert routes["OPTIONS /v1/{proxy+}"]["AuthorizationType"] == "NONE"


def test_authenticated_route_keeps_the_jwt_authorizer():
    routes = _routes(_template("RempartApiStack"))
    assert routes["ANY /v1/{proxy+}"]["AuthorizationType"] == "JWT"
    assert routes["POST /v1/events/deployment"]["AuthorizationType"] == "NONE"


def test_cors_origins_are_restricted_to_the_real_portal():
    api = _template("RempartApiStack").find_resources("AWS::ApiGatewayV2::Api")
    cors = next(iter(api.values()))["Properties"]["CorsConfiguration"]
    assert cors["AllowOrigins"] == [PORTAL_ORIGIN]
    assert "*" not in cors["AllowHeaders"]
    for header in ("Authorization", "Content-Type", "X-Rempart-Key"):
        assert header in cors["AllowHeaders"]
    assert "OPTIONS" in cors["AllowMethods"]


def test_lambda_receives_les_origines_cors_et_le_bucket_des_rapports():
    functions = _template("RempartApiStack").find_resources("AWS::Lambda::Function")
    env = next(iter(functions.values()))["Properties"]["Environment"]["Variables"]
    assert env["REMPART_CORS_ALLOW_ORIGINS"] == PORTAL_ORIGIN
    assert "REMPART_REPORTS_BUCKET" in env
    # Aucune valeur de secret en clair dans le template.
    assert "REMPART_PIPELINE_KEY" not in env


def test_pipeline_key_vient_de_ssm_sans_secret_en_clair(monkeypatch):
    """La clé du webhook est une référence dynamique SSM, jamais en clair."""
    monkeypatch.setenv("REMPART_PIPELINE_KEY_SSM_PARAM", "/rempart/dev/pipeline-key")
    functions = _template("RempartApiStack").find_resources("AWS::Lambda::Function")
    env = next(iter(functions.values()))["Properties"]["Environment"]["Variables"]
    reference = env["REMPART_PIPELINE_KEY"]
    rendered = json.dumps(reference)
    assert "resolve:ssm-secure:/rempart/dev/pipeline-key" in rendered
    assert "REMPART_PIPELINE_KEY" in env


def test_reports_bucket_is_private_encrypted_and_retained():
    buckets = _template("RempartStorageStack").find_resources("AWS::S3::Bucket")
    assert len(buckets) == 1, "le bucket des rapports doit exister (EF-RAP-04)"
    props = next(iter(buckets.values()))["Properties"]
    assert props["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }
    rules = props["LifecycleConfiguration"]["Rules"]
    assert rules[0]["ExpirationInDays"] == 396  # ENF-DATA-01 : 13 mois
    algorithm = props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]
    assert algorithm["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"


def test_api_lambda_can_write_the_evidence_dossier():
    """Sans droit d'écriture, la route 201 ne pourrait toujours rien stocker."""
    policies = _template("RempartApiStack").find_resources("AWS::IAM::Policy")
    statements = [
        statement
        for policy in policies.values()
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
    ]
    actions = {
        action
        for statement in statements
        for action in (
            statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
        )
    }
    # `grant_read_write` pose `s3:PutObject` et `s3:GetObject*` : on vérifie le
    # droit réel, pas une chaîne exacte.
    assert any(a.startswith("s3:PutObject") for a in actions)
    assert any(a.startswith("s3:GetObject") for a in actions)
