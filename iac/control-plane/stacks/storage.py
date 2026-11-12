"""DynamoDB storage stack for the Rempart control plane."""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_dynamodb as ddb
import aws_cdk.aws_s3 as s3
from constructs import Construct

from ._helpers import DEFAULT_TABLE_PREFIX, create_encrypted_table

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
    ("AuditTable", "audit", "audit_id", [("object_id-index", "object_id", None)]),
]


# ENF-DATA-01 : 13 mois de conservation, comme le TTL des tables DynamoDB
# (`common/store.DEFAULT_RETENTION_MONTHS`) — 13 × 30,4375 ≈ 396 jours.
REPORTS_RETENTION_DAYS = 396


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
        # Option A « 0 € strict » : chiffrement AWS-managed (gratuit). La clé
        # customer-managed à 1 $/mois reste possible plus tard en réactivant
        # create_kms_key — décision user du 11 nov 2026.
        self.kms_key = None
        self.tables: dict[str, ddb.Table] = {}
        self._create_all_tables()
        self.reports_bucket = self._create_reports_bucket()

    def _create_reports_bucket(self) -> s3.Bucket:
        """Bucket des rapports mensuels et dossiers de preuves (EF-RAP-04).

        INCIDENT RÉEL (12 nov. 2026, compte 710332178565) : `POST
        /v1/tenants/{id}/evidence` répondait 201 avec une clé S3 alors qu'aucun
        bucket de rapports n'existait dans le compte — le dossier n'était jamais
        conservé. Chiffrement AWS-managed et blocage public total : 0 €.
        """
        return s3.Bucket(
            self,
            "ReportsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=False,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ENF-DATA-01-retention",
                    expiration=cdk.Duration.days(REPORTS_RETENTION_DAYS),
                )
            ],
        )

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
            encryption_key=self.kms_key or None,
        )
