# CONTRAT — interfaces partagées du projet Rempart

> Ce fichier est le **contrat** entre tous les modules. Chaque module code
> contre ces signatures exactes. Toute modification d'interface se fait ICI
> d'abord. Cahier des charges : `docs/cahier-des-charges-tests-intrusion-continu.md`.

## Règles absolues (tous les modules)

- Fichier < **500 lignes**, fonction < **50 lignes**, zéro duplication.
- Python 3.12, type hints partout. Tests `pytest` sans réseau ni AWS réel
  (boto3/botocore stubbés ou clients fake injectés).
- **ENF-IA-01** : tout chiffre (KPI, coût, échéance) est calculé par du code
  déterministe, jamais par un modèle.
- Aucun import croisé entre `api`, `orchestrator`, `triage`, `reports` :
  ils ne dépendent QUE de `rempart.common`.
- UI portail et docs de soumission (HLD, README) **en anglais**.
  Commentaires de code : français ou anglais, cohérent par module.

## Arborescence

```
backend/
  pyproject.toml          # [tool.pytest.ini_options] pythonpath, testpaths ; [tool.ruff]
  rempart/
    __init__.py
    common/               # modèles, matrice, budget, empreinte, authz, store, config, timeutil
    api/                  # handlers HTTP (Lambda) — routes du chapitre 14
    orchestrator/         # tâches Step Functions + client Security Agent + tickets GitHub
    triage/               # agent de tri Strands + garde-fous
    reports/              # KPI déterministes + rapport mensuel HTML/PDF
  tests/
    common/ api/ orchestrator/ triage/ reports/ iac/ fakes.py
iac/
  control-plane/          # CDK Python (app.py + stacks)
  client-account/         # template CloudFormation du compte client
portal/                   # Vite + React + TypeScript (UI anglaise)
demo/
  app-a/  app-b/          # apps Flask à failles semées (flags env)
  gate/                   # workflow réutilisable « porte CI/CD »
docs/                     # HLD.md (EN), acceptance.md (R1–R12), cahier des charges
```

`backend/tests/fakes.py` (livré par le module common) fournit :
`FakeStore` (dict-backed, même interface que `Store`), `FakeSecurityAgentClient`,
`FakeModelClient` (réponses canned pour triage/reports), `FakeGitHub`.

## `rempart.common` — signatures exactes

### `timeutil.py`
```python
def utcnow() -> datetime                      # TZ-aware UTC
def iso(dt: datetime) -> str                  # "2026-11-10T23:00:00Z"
def parse_iso(s: str) -> datetime
```

### `models.py` — dataclasses, chacune avec `to_item() -> dict` / `classmethod from_item(d) -> Self`
```python
PLANS = ("essentiel", "continu", "critique")
SEVERITIES = ("Critical", "High", "Medium", "Low", "Informational")
CONFIDENCES = ("High", "Medium", "Low")
PRIORITIES = ("P1", "P2", "P3", "P4")
FINDING_STATUSES = ("new", "pending_validation", "confirmed", "false_positive",
                    "risk_accepted", "in_remediation", "to_retest", "closed", "reopened")
RUN_STATUSES = ("queued", "running", "completed", "failed", "stopped", "blocked")
TRIGGERS = ("cicd", "schedule", "manual", "retest")

@dataclass Tenant:        # tenant_id, name, aws_account_id, region, role_arn,
    # external_id, plan, contacts: list[dict], monthly_budget_hours: float,
    # mandate_status: "none"|"pending"|"valid"|"expired", created_at: str
@dataclass Application:   # app_id, tenant_id, name, criticality: "low"|"medium"|"high",
    # internet_exposed: bool, data_types: list[str] ("personal","payment","health","none"),
    # environment: "staging"|"production", agent_space_id: str|None, domains: list[str],
    # repositories: list[str], team: str, ticket_channel: str, context: dict, created_at: str
@dataclass TestConfig:    # config_id, app_id, sa_pentest_id, kind: "delivery"|"full"|"on_demand",
    # scope: dict, risk_types: list[str], blocking_threshold: str, schedule: str|None
@dataclass Run:           # run_id, config_id, app_id, tenant_id, trigger, commit_from,
    # commit_to, scope_decision: str, status, started_at, ended_at: str|None,
    # duration_s: float|None, task_hours: float|None, cost_usd: float|None
@dataclass Finding:       # finding_id, app_id, tenant_id, run_id, fingerprint, title,
    # risk_type, severity, confidence, priority, status, due_at: str|None,
    # ticket_url: str|None, remediation_pr_url: str|None, evidence: dict, cvss: dict,
    # created_at, updated_at, closed_at: str|None, closed_by_run_id: str|None
@dataclass Decision:      # decision_id, finding_id, author_type: "agent"|"human",
    # author, action, justification, created_at
@dataclass Report:        # report_id, tenant_id, period ("YYYY-MM"), s3_key, kpis: dict, created_at
@dataclass BudgetState:   # tenant_id, month ("YYYY-MM"), hours_used: float,
    # thresholds_hit: list[int], auto_stop: bool
@dataclass AuditEvent:    # audit_id, actor, action, object_type, object_id, result, created_at
```

### `priority.py` (chapitre 12.2 — matrice déterministe)
```python
@dataclass PriorityResult: priority: str; needs_validation: bool

def compute_priority(severity: str, confidence: str, *,
                     exposed_critical: bool, sensitive_data: bool) -> PriorityResult
# Matrice (exposed_critical = internet_exposed AND criticality == "high") :
#   Critical+High -> P1 ; Critical+Med/Low -> P1 si exposed sinon P2, needs_validation=True
#   High+High -> P1 si exposed sinon P2 ; High+Med/Low -> P2 si exposed sinon P3, needs_validation=True
#   Medium+High -> P2 si exposed sinon P3 ; Medium+Med/Low -> P3 si exposed sinon P4
#   Low|Informational (toute confiance) -> P4
# sensitive_data (personal|payment|health dans data_types) : monte d'un cran
#   (P4->P3->P2->P1), plafonné à P1. needs_validation inchangé par ce cran.

DEFAULT_DUE_DAYS = {"P1": 7, "P2": 30, "P3": 90, "P4": None}
def due_date(priority: str, created_at: datetime,
             due_days: dict | None = None) -> datetime | None   # P4 -> None
```

### `fingerprint.py`
```python
def fingerprint(app_id: str, risk_type: str, entry_point: str,
                parameter: str | None = None) -> str   # sha256 hex, 16 premiers caractères
```

### `budget.py`
```python
DEFAULT_HOURLY_RATE = 50.0
def estimate_cost(task_hours: float, hourly_rate: float = DEFAULT_HOURLY_RATE) -> float
@dataclass BudgetVerdict: allowed: bool; pct: float; newly_crossed: list[int]; auto_stop: bool
def check_budget(state: BudgetState, monthly_budget_hours: float,
                 hourly_rate: float = DEFAULT_HOURLY_RATE) -> BudgetVerdict
# seuils 50/80/100 ; auto_stop à >= 100 % (réglable : state.auto_stop force l'arrêt)
def consume(state: BudgetState, task_hours: float,
            monthly_budget_hours: float) -> tuple[BudgetState, BudgetVerdict]
```

### `tenant.py` (autorisation — EF-POR-01, ENF-SEC-01)
```python
ROLES = ("platform_admin", "analyst", "account_manager",
         "client_security", "client_dev", "executive", "demo")
class AuthError(Exception): ...        # .status_code = 403 (401 si claims invalides)
@dataclass Principal: user_id: str; role: str; tenant_id: str | None
def resolve_principal(jwt_claims: dict) -> Principal
# lit claims Cognito : "cognito:groups" (premier rôle connu), "sub", "custom:tenant_id"
def authorize_read(p: Principal, tenant_id: str) -> None    # lève AuthError
def authorize_write(p: Principal, tenant_id: str) -> None   # lève AuthError
# platform_admin/analyst : tous tenants (read ; write = analyst+admin)
# account_manager : read tous, write aucun ; client_* : son tenant seulement ;
# executive : rapports seulement (géré côté api) ; demo : read-only tenant "demo"
```

### `store.py` (DynamoDB — injection obligatoire pour les tests)
```python
class Store:
    def __init__(self, ddb_resource=None, table_prefix: str = "rempart-"): ...
    # tables : tenants, applications, test-configs, runs, findings,
    #          decisions, reports, budget, audit
    # Chaque entité : PK évidente (tenant_id, app_id, run_id, finding_id,
    # decision_id, report_id, "tenant_id#month", audit_id) ; GSI côté CDK.
    def save_tenant(t: Tenant) -> Tenant
    def get_tenant(tenant_id) -> Tenant | None
    def list_tenants() -> list[Tenant]
    def save_application(a: Application) -> Application
    def get_application(app_id) -> Application | None
    def list_applications(tenant_id: str | None = None) -> list[Application]
    def save_config(c: TestConfig) -> TestConfig
    def list_configs(app_id) -> list[TestConfig]
    def save_run(r: Run) -> Run
    def get_run(run_id) -> Run | None
    def list_runs(app_id=None, tenant_id=None, status=None, limit=50) -> list[Run]
    def save_finding(f: Finding) -> Finding
    def get_finding(finding_id) -> Finding | None
    def list_findings(tenant_id=None, app_id=None, status=None, priority=None, limit=100) -> list[Finding]
    def find_by_fingerprint(app_id: str, fingerprint: str) -> Finding | None
    def save_decision(d: Decision) -> Decision
    def list_decisions(finding_id) -> list[Decision]
    def save_report(r: Report) -> Report
    def get_report(report_id) -> Report | None
    def list_reports(tenant_id) -> list[Report]
    def get_budget(tenant_id, month) -> BudgetState
    def save_budget(b: BudgetState) -> BudgetState
    def append_audit(actor, action, object_type, object_id, result="ok") -> AuditEvent
    def list_audit(object_type=None, object_id=None, limit=100) -> list[AuditEvent]
```

### `config.py`
```python
@dataclass Settings:
    table_prefix: str = "rempart-"
    region: str = "eu-west-3"
    hourly_rate: float = 50.0
    github_api: str = "https://api.github.com"
    github_owner: str = ""
    sa_endpoint_url: str | None = None     # None = boto3 par défaut
    @classmethod
    def from_env(cls) -> "Settings"        # préfixe REMPART_
```

## `rempart.api` — routes (chapitre 14)

`app.py` expose `lambda_handler(event, context)` (API Gateway HTTP API v2 :
`event["requestContext"]["http"]["method"]`, `event["rawPath"]`,
`event.get("queryStringParameters")`, `event.get("body")` JSON, claims JWT dans
`event["requestContext"]["authorizer"]["jwt"]["claims"]`).

Chaque module de route expose `register(router)` où
`router.add(method, path_pattern, handler)` ; `handler(ctx: ApiContext) -> tuple[int, dict]`.
`ApiContext` : `.principal`, `.path_params: dict`, `.query: dict`, `.body: dict`,
`.store`, `.settings`, `.sa` (SecurityAgentClient), `.audit(action, obj_type, obj_id, result)`.

Routes : tenants (POST/GET/GET{id}), applications (POST sous tenant, GET{id}),
onboarding (POST/GET), runs (POST/GET par app), run (GET/POST stop par jobId),
events/deployment (POST, clé pipeline — pas de JWT), findings (GET filtres
tenant/status/priority, GET{id}), decision (POST), remediation (POST),
kpis (GET tenant + GET fleet), reports (POST tenant / GET{id}),
budget (GET/PUT tenant).
**Chaque handler vérifie l'autorisation AVANT toute lecture** (R9 : tests
négatifs obligatoires : principal du tenant A sur ressource du tenant B -> 403
sur chaque point d'API).

## `rempart.orchestrator`

### `sa_client.py`
```python
class SecurityAgentClient:
    def __init__(self, boto_client=None, endpoint_url=None, region="eu-west-3"): ...
    # boto3.client("securityagent") ; méthodes 1:1 avec l'API (noms du chapitre 11.6) :
    def create_agent_space(self, name: str, **kw) -> dict
    def create_target_domain(self, space_id: str, domain: str, **kw) -> dict
    def verify_target_domain(self, space_id: str, domain_id: str) -> dict
    def create_pentest(self, space_id: str, config: dict) -> dict
    def start_pentest_job(self, pentest_id: str, **kw) -> dict   # {"jobId": ...}
    def stop_pentest_job(self, job_id: str) -> dict
    def batch_get_pentest_jobs(self, job_ids: list[str]) -> list[dict]
    def list_pentests(self, space_id: str) -> list[dict]
    def list_findings(self, job_id: str) -> list[dict]
    def update_finding(self, finding_id: str, **kw) -> dict
    def start_code_remediation(self, finding_id: str, **kw) -> dict
```
Le `FakeSecurityAgentClient` (tests/fakes.py) implémente exactement la même
interface, avec des scénarios scriptables (findings semées, job qui réussit/échoue).

### Tâches Step Functions (`tasks.py` — chacune `(payload: dict, deps: Deps) -> dict`)
```python
@dataclass Deps: store: Store; sa: SecurityAgentClient; settings: Settings;
                 github: GitHubClient | None = None; model_client=None
def budget_gate(payload, deps) -> dict       # {"allowed": bool, ...} refuse si mandat != "valid" (R12) ou budget épuisé (R8)
def start_run(payload, deps) -> dict         # StartPentestJob -> run_id, status "running"
def poll_run(payload, deps) -> dict          # BatchGetPentestJobs ; maj Run (heures-tâches, coût, durée) ; stop auto si budget dépassé
def collect_findings(payload, deps) -> dict  # ListFindings -> Finding(new) avec fingerprint ; détection doublon + régression (EF-TRI-01/06)
def dispatch_triage(payload, deps) -> dict   # appelle triage.run_triage, applique les garde-fous, écrit Decisions(agent) ; critique/élevée -> "pending_validation"
def create_tickets(payload, deps) -> dict    # findings confirmed -> ticket GitHub avec échéance (EF-COR-01/02)
def request_remediation(payload, deps) -> dict  # StartCodeRemediation -> lien PR (EF-COR-03)
def close_or_reopen(payload, deps) -> dict   # retest : disparue -> closed + preuve ; présente -> in_remediation (EF-COR-04/05)
```

### `discovery.py`
```python
def discover_cicd_runs(deps: Deps, since_minutes: int = 5) -> list[Run]
# interroge les jobs des configs "delivery" (EF-ORC-01) et crée les Runs manquants
```

### `github_client.py`
```python
class GitHubClient:
    def __init__(self, token: str, api: str = "https://api.github.com"): ...
    def create_issue(self, owner: str, repo: str, title: str, body: str,
                     labels: list[str]) -> dict      # {"html_url": ...}
    def close_issue(self, owner: str, repo: str, number: int, comment: str) -> None
```
`FakeGitHub` dans tests/fakes.py (même interface, en mémoire).

## `rempart.triage`

```python
# proposal.py
@dataclass TriageProposal:            # format annexe B, clés JSON camelCase via to_dict()
    finding_id: str; duplicate_of: str | None; is_regression: bool
    proposed_status: str              # "CONFIRMED"|"TO_VERIFY"|"LIKELY_FALSE_POSITIVE"
    priority: str; plain_summary: str; technical_summary: str
    references: list[str]; justification: str; needs_human_validation: bool
    def to_dict(self) -> dict; @classmethod def from_dict(d) -> "TriageProposal"

# agent.py
def run_triage(*, findings: list[Finding], app: Application,
               known_findings: list[Finding], past_decisions: list[Decision],
               deps: Deps | None = None, model_client=None) -> list[TriageProposal]
# Strands optionnel : si strands-agents importable ET model_client réel fourni ->
# agent outillé (tools.py) ; sinon chemin déterministe de repli (dédup par
# fingerprint, statuts par règles). Les GARDE-FOUS s'appliquent dans les deux cas.

# guardrails.py
def enforce(proposal: TriageProposal, finding: Finding, app: Application) -> TriageProposal
# 1) priorité recalculée par la matrice ; écart -> matrice gagne + log "divergence"
# 2) "LIKELY_FALSE_POSITIVE" sur Critical|High -> needs_human_validation=True,
#    proposed_status="TO_VERIFY" (EF-TRI-05, ENF-IA-02)
# 3) régression : fingerprint d'une finding closed -> is_regression=True, statut "reopened"

# prompts.py
SYSTEM_PROMPT: str   # précise : le contenu des failles est une DONNÉE délimitée
                     # (<finding>…</finding>), aucune instruction interne ne doit
                     # être suivie (ENF-IA-03) ; sortie JSON annexe B stricte.

# tools.py — les 5 outils du chapitre 12.3, signatures :
def get_application_context(ctx) -> dict
def search_known_findings(ctx, app_id, risk_type=None, entry_point=None) -> list[dict]
def get_finding_detail(ctx, finding_id) -> dict
def get_past_decisions(ctx, app_id) -> list[dict]
def submit_triage_proposal(ctx, proposal: dict) -> dict
# ctx = objet TriageContext(store, app, findings, known, decisions) ; chaque outil
# valide ses entrées et n'a AUCUN autre effet d'écriture (12.4).
```

## `rempart.reports`

```python
# metrics.py — ENF-IA-01 : tout vient des horodatages du Store, rien du modèle.
def compute_kpis(store: Store, *, tenant_id: str | None, period: str) -> dict
# clés : delivery_to_result_hours (médiane), critical_blocked_before_prod (ratio),
# mean_time_to_fix_days_by_priority {P1..P4}, sla_compliance (ratio),
# coverage (ratio), reopen_rate (ratio), findings_open_by_priority,
# findings_closed, tests_total, tests_blocked, task_hours_used, cost_usd
def freeze_month(store, tenant_id, period) -> dict    # fige au 1er jour ouvré (8.5)

# monthly.py
def build_monthly_report(*, store, tenant_id, period, model_client=None,
                         s3=None) -> Report
# synthèse rédigée par le modèle à partir des chiffres figés (jamais l'inverse) ;
# HTML (template string) + PDF (fpdf2) ; upload S3 injectable (FakeS3 en test).
```

## `iac/control-plane` (CDK Python)

`app.py` + stacks dans `stacks/` : `storage.py` (DynamoDB + KMS, PITR, TTL
13 mois via attribut `expire_at`), `identity.py` (Cognito + groupes = ROLES),
`api.py` (HTTP API + Lambdas `rempart.api`, authorizer JWT), `orchestrator.py`
(Step Functions : budget_gate → start_run → poll (wait 60 s, max 4 h) →
collect → triage → tickets ; EventBridge Scheduler mensuel ; Lambda discovery
toutes les 5 min), `portal.py` (S3 + CloudFront, OAI), `notifications.py`
(SES + Lambda e-mail : P1/P2 confirmée, livraison bloquée, échéance dépassée,
seuil budget). Variables d'env des Lambdas préfixées `REMPART_`.
Test obligatoire : `tests/iac/test_synth.py` synthétise l'app avec
account/region factices et assertit la présence des ressources clés.

## `iac/client-account/rempart-client.template.yaml`

Paramètres : `MspAccountId`, `MspOrchestratorRoleName`, `ExternalId`,
`GitHubOrg`, `GitHubRepo`. Ressources : rôle d'exploitation inter-comptes
(trust = rôle orchestrateur MSP + condition `sts:ExternalId`, permissions =
annexe A du cahier des charges), rôle OIDC GitHub (planification/lancement),
CloudWatch Log Groups (`/rempart/pipeline`, rétention 400 j), AWS::Budgets::Budget
avec alarmes. Test : `tests/iac/test_client_template.py` (yaml valide, rôle +
condition ExternalId + actions `securityagent:` présentes).

## `portal/` (Vite + React 18 + TS + react-router)

UI **anglaise**. Pages : `Login`, `Fleet` (tous tenants, KPI chapitre 4),
`Tenant`, `Application`, `Run`, `Finding`, `TriageQueue` (confirmer/corriger
en un clic, EF-TRI), `Reports`, `Budget`. `src/api/client.ts` : fetch typé
vers les routes `/v1/*` (base URL par `import.meta.env.VITE_API_URL`).
Compte démo : bannière "Judge demo — read-only" quand rôle `demo` (EF-POR-03).
Tests vitest : `client.ts` (mock fetch), `TriageQueue` (render + clic
confirmer), `priority` badge mapping. `npm run build` doit passer.

## `demo/`

- `app-a/` **ShopLite** (client A) : `GET /health`, `GET /orders/<id>`,
  `GET /orders` (liste de l'utilisateur). Faille semée IDOR si
  `VULN_IDOR=1` (défaut) : `/orders/<id>` ne vérifie pas le propriétaire
  (header `X-User-Id`). SQLite en mémoire, données de démo.
- `app-b/` **BookWorm** (client B) : `GET /health`, `GET /search?q=`
  (SQLi si `VULN_SQLI=1`), `GET /admin/users` (sans auth si `VULN_ADMIN=1`).
- Chaque app : `app.py` (factory `create_app()`), `requirements.txt`,
  `seed.py`, `tests/test_app.py` (comportement vulnérable ET corrigé selon
  les flags), `Dockerfile`.
- `gate/pentest-gate.yml` : workflow réutilisable GitHub Actions — POST
  `/v1/events/deployment` + appel de la porte Security Agent (action/CLI
  documentée en commentaire), `timeout-minutes: 5`.

## Variables d'environnement (Lambda)

`REMPART_TABLE_PREFIX`, `REMPART_REGION`, `REMPART_HOURLY_RATE`,
`REMPART_GITHUB_TOKEN` (via Secrets Manager en prod, `GITHUB_TOKEN` en test),
`REMPART_GITHUB_OWNER`, `HERMES_*` inchangées.

## Définition de fini par module

1. `cd backend && ../.venv/bin/python -m pytest tests/<zone> -q` vert.
2. `../.venv/bin/ruff check rempart/<zone> tests/<zone>` clean.
3. `wc -l` : aucun fichier ≥ 500 lignes ; aucune fonction ≥ 50 lignes.
4. Les tests n'utilisent que des fakes (zéro appel réseau/AWS).
