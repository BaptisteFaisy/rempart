"""Data models for Rempart."""

from dataclasses import asdict, dataclass
from typing import Any, Self

PLANS = ("essentiel", "continu", "critique")
SEVERITIES = ("Critical", "High", "Medium", "Low", "Informational")
CONFIDENCES = ("High", "Medium", "Low")
PRIORITIES = ("P1", "P2", "P3", "P4")
FINDING_STATUSES = (
    "new",
    "pending_validation",
    "confirmed",
    "false_positive",
    "risk_accepted",
    "in_remediation",
    "to_retest",
    "closed",
    "reopened",
)
RUN_STATUSES = ("queued", "running", "completed", "failed", "stopped", "blocked")
TRIGGERS = ("cicd", "schedule", "manual", "retest")


class _ItemMixin:
    """Provides to_item() and from_item() helpers for dataclasses."""

    __test__ = False

    def to_item(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_item(cls, d: dict[str, Any]) -> Self:
        fields = cls.__dataclass_fields__  # type: ignore[attr-defined]
        filtered = {k: v for k, v in d.items() if k in fields}
        return cls(**filtered)


@dataclass
class Tenant(_ItemMixin):
    tenant_id: str
    name: str
    aws_account_id: str
    region: str
    role_arn: str
    external_id: str
    plan: str
    contacts: list[dict[str, Any]]
    monthly_budget_hours: float
    mandate_status: str
    created_at: str
    # Éligibilité au free tier AWS Continuum confirmée dans la console : tant
    # que ce n'est pas vrai, le garde-fou refuse de lancer un test réel.
    free_tier_confirmed: bool = False


@dataclass
class Application(_ItemMixin):
    app_id: str
    tenant_id: str
    name: str
    criticality: str
    internet_exposed: bool
    data_types: list[str]
    environment: str
    agent_space_id: str | None
    domains: list[str]
    repositories: list[str]
    team: str
    ticket_channel: str
    context: dict[str, Any]
    created_at: str


@dataclass
class TestConfig(_ItemMixin):
    config_id: str
    app_id: str
    sa_pentest_id: str
    kind: str
    scope: dict[str, Any]
    risk_types: list[str]
    blocking_threshold: str
    schedule: str | None


@dataclass
class Run(_ItemMixin):
    run_id: str
    config_id: str
    app_id: str
    tenant_id: str
    trigger: str
    commit_from: str
    commit_to: str
    scope_decision: str
    status: str
    started_at: str
    ended_at: str | None
    duration_s: float | None
    task_hours: float | None
    cost_usd: float | None


@dataclass
class Finding(_ItemMixin):
    finding_id: str
    app_id: str
    tenant_id: str
    run_id: str
    fingerprint: str
    title: str
    risk_type: str
    severity: str
    confidence: str
    priority: str
    status: str
    due_at: str | None
    ticket_url: str | None
    remediation_pr_url: str | None
    evidence: dict[str, Any]
    cvss: dict[str, Any]
    created_at: str
    updated_at: str
    closed_at: str | None
    closed_by_run_id: str | None


@dataclass
class Decision(_ItemMixin):
    decision_id: str
    finding_id: str
    author_type: str
    author: str
    action: str
    justification: str
    created_at: str


@dataclass
class Report(_ItemMixin):
    report_id: str
    tenant_id: str
    period: str
    s3_key: str
    kpis: dict[str, Any]
    created_at: str


@dataclass
class BudgetState(_ItemMixin):
    tenant_id: str
    month: str
    hours_used: float
    thresholds_hit: list[int]
    auto_stop: bool


@dataclass
class AuditEvent(_ItemMixin):
    audit_id: str
    actor: str
    action: str
    object_type: str
    object_id: str
    result: str
    created_at: str
