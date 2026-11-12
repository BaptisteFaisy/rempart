"""Lectures AWS du script de preuves : S3, DynamoDB, Lambda.

Isolées pour que `proof_real.py` reste lisible et sous la limite de 500 lignes.
Ces fonctions ne font QUE lire : aucune écriture sur l'environnement observé.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

REGION = os.environ.get("AWS_REGION", "eu-north-1")
PREFIX = "rempart-"


def sha256_of_pack(pack: dict[str, Any]) -> str:
    """SHA-256 canonique, implémentation indépendante de celle de Rempart."""
    payload = {k: v for k, v in pack.items() if k not in ("integrity", "s3_key")}
    canonical = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def list_bucket_names() -> list[str]:
    """Buckets du compte (lecture seule)."""
    import boto3

    client = boto3.client("s3", region_name=REGION)
    return [b["Name"] for b in client.list_buckets().get("Buckets", [])]


def fetch_stored_object(key: str) -> dict[str, Any] | None:
    """Retélécharge l'objet S3 annoncé, quel que soit le bucket qui le porte.

    On cherche réellement : le dossier de preuves peut être dans n'importe quel
    bucket du compte, et l'absence de l'objet est un résultat à mesurer, pas
    une erreur à masquer.
    """
    import boto3

    client = boto3.client("s3", region_name=REGION)
    for bucket in list_bucket_names():
        try:
            raw = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        except Exception:  # noqa: BLE001, S112 — on cherche dans tous les buckets
            continue
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def scan_runs() -> list[dict[str, Any]]:
    """Toutes les lignes de `rempart-runs` (scan brut, hors Store de l'app)."""
    import boto3
    from boto3.dynamodb.types import TypeDeserializer

    client = boto3.client("dynamodb", region_name=REGION)
    deserializer = TypeDeserializer()
    rows: list[dict[str, Any]] = []
    last: dict[str, Any] | None = None
    while True:
        kwargs: dict[str, Any] = {"TableName": f"{PREFIX}runs"}
        if last:
            kwargs["ExclusiveStartKey"] = last
        page = client.scan(**kwargs)
        rows.extend(deserializer.deserialize({"M": item}) for item in page.get("Items", []))
        last = page.get("LastEvaluatedKey")
        if not last:
            return rows


def api_function() -> dict[str, Any] | None:
    """Configuration de la Lambda API déployée (nom, code, date, variables)."""
    import boto3

    client = boto3.client("lambda", region_name=REGION)
    functions = [
        f
        for f in client.list_functions().get("Functions", [])
        if f["FunctionName"].startswith("RempartApiStack-RempartApiFunction")
    ]
    if not functions:
        return None
    function = functions[0]
    return {
        "name": function["FunctionName"],
        "last_modified": function.get("LastModified", ""),
        "runtime": function.get("Runtime", ""),
        "variables": function.get("Environment", {}).get("Variables", {}),
    }
