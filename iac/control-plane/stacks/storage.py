"""DynamoDB storage stack for the Rempart control plane."""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_dynamodb as ddb
import aws_cdk.aws_kms as kms
from constructs import Construct

from ._helpers import DEFAULT_TABLE_PREFIX, create_encrypted_table, create_kms_key

TABLE_SPECS: list[tuple[str, str, str, list[tuple[str, str, str | None]]]] = [
    ("TenantsTable", "tenants", "tenant_id", []),
    ("ApplicationsTable", "applications", "app_id", [("tenant_id-index", "tenant_id", None)]),
    ("TestConfigsTable", "test-configs", "config_id", [("app_id-index", "app_id", None)]),
    (
        "RunsTable",
        "runs",
        "run_id",
        [("app_id-index", "app_id", None), ("tenant_id-index", "tenant_id", None)],
    ),
    (
        "FindingsTable",
        "findings",
        "finding_id",
        [
            ("app_id-fingerprint-index", "app_id", "fingerprint"),
            ("tenant_id-index", "tenant_id", None),
        ],
    ),
    ("DecisionsTable", "decisions", "decision_id", [("finding_id-index", "finding_id", None)]),
    ("ReportsTable", "reports", "report_id", [("tenant_id-index", "tenant_id", None)]),
    ("BudgetTable", "budget", "pk", []),
    ("AuditTable", "audit", "audit_id", []),
]


class StorageStack(cdk.Stack):
    """Provisions the 9 DynamoDB tables required by Rempart."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        table_prefix: str = DEFAULT_TABLE_PREFIX,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.table_prefix = table_prefix
        self.kms_key: kms.Key = create_kms_key(
            self, "RempartStorageKey", alias="alias/rempart/storage"
        )
        self.tables: dict[str, ddb.Table] = {}
        self._create_all_tables()

    def _create_all_tables(self) -> None:
        for construct_id, name, pk_name, gsis in TABLE_SPECS:
            table = self._add_table(
                construct_id,
                name,
                ddb.Attribute(name=pk_name, type=ddb.AttributeType.STRING),
            )
            for idx_name, gsi_pk, gsi_sk in gsis:
                sk_attr = (
                    ddb.Attribute(name=gsi_sk, type=ddb.AttributeType.STRING)
                    if gsi_sk
                    else None
                )
                table.add_global_secondary_index(
                    index_name=idx_name,
                    partition_key=ddb.Attribute(name=gsi_pk, type=ddb.AttributeType.STRING),
                    sort_key=sk_attr,
                )
            self.tables[name] = table

    def _add_table(
        self,
        construct_id: str,
        logical_name: str,
        partition_key: ddb.Attribute,
        sort_key: ddb.Attribute | None = None,
    ) -> ddb.Table:
        return create_encrypted_table(
            self,
            construct_id,
            table_name=f"{self.table_prefix}{logical_name}",
            partition_key=partition_key,
            sort_key=sort_key,
            encryption_key=self.kms_key,
        )
