"""Step Functions orchestration stack for Rempart (CONTRACT-PHASE0 section 3).

Three short, bounded state machines instead of one long one:

* ``RempartPentestLifecycle`` (A) — Rempart starts the pentest, polls it under a
  4 h cap, triages the findings, opens tickets and requests remediation.
* ``RempartCicdIntake`` (B) — the client CI/CD gate already ran and finished the
  test: same tail as A, without ``budget_gate``, ``start_run`` and ``poll_run``.
* ``RempartRetestClose`` (C) — the retest run decides closure with proof or
  reopening on regression (cahier des charges section 8.4).

Every task Lambda points at ``rempart.orchestrator.lambda_handlers.<name>``; the
contract test ``tests/iac/test_handler_contract.py`` enforces that invariant.
"""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_dynamodb as ddb
import aws_cdk.aws_events as events
import aws_cdk.aws_events_targets as targets
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as _lambda
import aws_cdk.aws_stepfunctions as sfn
import aws_cdk.aws_stepfunctions_tasks as tasks
from constructs import Construct

from ._helpers import (
    DEFAULT_TABLE_PREFIX,
    create_python_lambda,
    handler_reference,
    runtime_layer,
)

HANDLER_MODULE = "rempart.orchestrator.lambda_handlers"

# The nine handlers fixed by CONTRACT-PHASE0 section 2, in lifecycle order.
TASK_NAMES = (
    "budget_gate",
    "start_run",
    "poll_run",
    "collect_findings",
    "dispatch_triage",
    "create_tickets",
    "request_remediation",
    "close_or_reopen",
    "discover_runs",
)

POLL_INTERVAL_SECONDS = 60
# 240 x 60 s = 4 h of polling (ENF-PERF-01, cahier des charges 11.4).
MAX_POLL_ITERATIONS = 240
DISCOVERY_INTERVAL_MINUTES = 5


def non_empty_array(path: str) -> sfn.Condition:
    """True when a JSONPath array holds at least one element.

    Step Functions has no list-equality operator, so ``$.closed != []`` and
    friends are expressed through the presence of their first element.
    """
    return sfn.Condition.is_present(f"{path}[0]")


def loop_cap_reached(path: str, cap: int) -> sfn.Condition:
    """True when a loop counter exists and reached ``cap``."""
    return sfn.Condition.and_(
        sfn.Condition.is_present(path),
        sfn.Condition.number_greater_than_equals(path, cap),
    )


class OrchestratorStack(cdk.Stack):
    """Provisions the three Step Functions machines and their task Lambdas."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        tables: dict[str, ddb.ITable],
        table_prefix: str = DEFAULT_TABLE_PREFIX,
        hourly_rate: float = 50.0,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        common_env = {
            "REMPART_TABLE_PREFIX": table_prefix,
            "REMPART_REGION": self.region,
            "REMPART_HOURLY_RATE": str(hourly_rate),
            # Garde-fous anti-facture : aucun test reel sans eligibilite
            # free tier confirmee, et un plafond d'heures-taches par test.
            "REMPART_FREE_TIER_ONLY": "1",
            "REMPART_MAX_TASK_HOURS_PER_TEST": "5",
        }
        self.lambdas: dict[str, _lambda.Function] = {
            name: self._create_task_lambda(name, common_env, tables) for name in TASK_NAMES
        }
        # Alias explicite : la decouverte est planifiee toutes les 5 min.
        self.discovery_lambda = self.lambdas["discover_runs"]
        self.pentest_lifecycle = self._build_pentest_lifecycle()
        self.cicd_intake = self._build_cicd_intake()
        self.retest_close = self._build_retest_close()
        # La decouverte demarre B (un run par run decouvert) et C (run de retest
        # arrive a l'etat terminal) : elle est le seul observateur des runs.
        self.cicd_intake.grant_start_execution(self.discovery_lambda)
        self.retest_close.grant_start_execution(self.discovery_lambda)
        self._setup_schedules()

    # ------------------------------------------------------------------ #
    # Lambdas
    # ------------------------------------------------------------------ #
    def _layers(self) -> list:
        """Layer des dépendances tierces (mémoïsé) ; vide s'il n'est pas construit."""
        if not hasattr(self, "_runtime_layer_cache"):
            layer = runtime_layer(self, "RempartRuntimeLayer")
            self._runtime_layer_cache = [layer] if layer else []
        return self._runtime_layer_cache

    def _create_task_lambda(
        self,
        name: str,
        env: dict[str, str],
        tables: dict[str, ddb.ITable],
    ) -> _lambda.Function:
        fn = create_python_lambda(
            self,
            f"Lambda{name.title().replace('_', '')}",
            handler=handler_reference(HANDLER_MODULE, name),
            environment=env,
            layers=self._layers(),
            timeout_seconds=300,
            memory_size=1024,
        )
        for table in tables.values():
            table.grant_read_write_data(fn)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=["arn:aws:iam::*:role/rempart-ops-role"],
            )
        )
        return fn

    # ------------------------------------------------------------------ #
    # Building blocks shared by the machines
    # ------------------------------------------------------------------ #
    def _invoke(
        self, scope: Construct, id_: str, task: str, state_name: str
    ) -> tasks.LambdaInvoke:
        return tasks.LambdaInvoke(
            scope,
            id_,
            lambda_function=self.lambdas[task],
            output_path="$.Payload",
            state_name=state_name,
        )

    def _findings_tail(self, scope: Construct) -> sfn.IChainable:
        """collect_findings -> CleanRun, or triage -> tickets -> remediation."""
        collect = self._invoke(scope, "CollectFindingsTask", "collect_findings", "CollectFindings")
        triage = self._invoke(scope, "DispatchTriageTask", "dispatch_triage", "DispatchTriage")
        tickets = self._invoke(scope, "CreateTicketsTask", "create_tickets", "CreateTickets")
        remediation = self._invoke(
            scope, "RequestRemediationTask", "request_remediation", "RequestRemediation"
        )
        clean = sfn.Succeed(scope, "CleanRunState", state_name="CleanRun")
        requested = sfn.Succeed(
            scope, "RemediationRequestedState", state_name="RemediationRequested"
        )
        collect.next(
            sfn.Choice(scope, "HasFindingsChoice", state_name="HasFindings")
            .when(non_empty_array("$.findings_created"), triage)
            .otherwise(clean)
        )
        triage.next(tickets).next(remediation).next(requested)
        return collect

    # ------------------------------------------------------------------ #
    # Machine A — RempartPentestLifecycle
    # ------------------------------------------------------------------ #
    def _poll_loop(self, scope: Construct, tail: sfn.IChainable) -> sfn.IChainable:
        """start_run -> poll every 60 s under the 4 h cap -> findings tail."""
        wait = sfn.Wait(
            scope,
            "PollWait",
            state_name="WaitBeforeNextPoll",
            time=sfn.WaitTime.duration(cdk.Duration.seconds(POLL_INTERVAL_SECONDS)),
        )
        poll = self._invoke(scope, "PollRunTask", "poll_run", "PollRun")
        timeout = sfn.Fail(
            scope,
            "PentestTimeoutState",
            state_name="PentestTimeout",
            error="PentestTimeout",
            cause=f"Polling exceeded {MAX_POLL_ITERATIONS} iterations (4 h cap)",
        )
        not_completed = sfn.Fail(
            scope,
            "PentestNotCompletedState",
            state_name="PentestNotCompleted",
            error="PentestNotCompleted",
            cause="Security Agent run ended with a status other than 'completed'",
        )
        completed = (
            sfn.Choice(scope, "IsRunCompletedChoice", state_name="IsRunCompleted")
            .when(sfn.Condition.string_equals("$.run_status", "completed"), tail)
            .otherwise(not_completed)
        )
        finished = (
            sfn.Choice(scope, "IsRunDoneChoice", state_name="IsRunDone")
            .when(sfn.Condition.boolean_equals("$.done", True), completed)
            .otherwise(wait)
        )
        capped = (
            sfn.Choice(scope, "IsPentestTimedOutChoice", state_name="IsPentestTimedOut")
            .when(loop_cap_reached("$.iterations", MAX_POLL_ITERATIONS), timeout)
            .otherwise(finished)
        )
        poll.next(capped)
        wait.next(poll)
        start = self._invoke(scope, "StartRunTask", "start_run", "StartRun")
        start.next(wait)
        return start

    def _build_pentest_lifecycle(self) -> sfn.StateMachine:
        scope = Construct(self, "PentestLifecycleScope")
        start = self._poll_loop(scope, self._findings_tail(scope))
        gate = self._invoke(scope, "BudgetGateTask", "budget_gate", "BudgetGate")
        refused = sfn.Succeed(scope, "RefusedState", state_name="Refused")
        gate.next(
            sfn.Choice(scope, "IsBudgetAllowedChoice", state_name="IsBudgetAllowed")
            .when(sfn.Condition.boolean_equals("$.allowed", True), start)
            .otherwise(refused)
        )
        return sfn.StateMachine(
            self,
            "PentestLifecycleMachine",
            state_machine_name="RempartPentestLifecycle",
            definition_body=sfn.DefinitionBody.from_chainable(gate),
            timeout=cdk.Duration.hours(4),
        )

    # ------------------------------------------------------------------ #
    # Machine B — RempartCicdIntake
    # ------------------------------------------------------------------ #
    def _build_cicd_intake(self) -> sfn.StateMachine:
        """The CI/CD gate of the client already ran the test: no poll, no gate."""
        scope = Construct(self, "CicdIntakeScope")
        return sfn.StateMachine(
            self,
            "CicdIntakeMachine",
            state_machine_name="RempartCicdIntake",
            definition_body=sfn.DefinitionBody.from_chainable(self._findings_tail(scope)),
            timeout=cdk.Duration.minutes(15),
        )

    # ------------------------------------------------------------------ #
    # Machine C — RempartRetestClose
    # ------------------------------------------------------------------ #
    def _build_retest_close(self) -> sfn.StateMachine:
        """Closure with proof (8.4) or reopening on regression."""
        scope = Construct(self, "RetestCloseScope")
        close = self._invoke(scope, "CloseOrReopenTask", "close_or_reopen", "CloseOrReopen")
        outcome = (
            sfn.Choice(scope, "RetestOutcomeChoice", state_name="RetestOutcome")
            .when(
                non_empty_array("$.closed"),
                sfn.Succeed(scope, "ClosedState", state_name="ClosedWithProof"),
            )
            .when(
                non_empty_array("$.reopened"),
                sfn.Succeed(scope, "ReopenedState", state_name="RegressionReopened"),
            )
            .otherwise(sfn.Succeed(scope, "NoChangeState", state_name="NoChange"))
        )
        close.next(outcome)
        return sfn.StateMachine(
            self,
            "RetestCloseMachine",
            state_machine_name="RempartRetestClose",
            definition_body=sfn.DefinitionBody.from_chainable(close),
            timeout=cdk.Duration.minutes(5),
        )

    # ------------------------------------------------------------------ #
    # Scheduling
    # ------------------------------------------------------------------ #
    def _setup_schedules(self) -> None:
        """Poll discovered CI/CD runs every 5 min; start machine A monthly."""
        events.Rule(
            self,
            "DiscoveryEvery5MinRule",
            schedule=events.Schedule.rate(cdk.Duration.minutes(DISCOVERY_INTERVAL_MINUTES)),
            targets=[targets.LambdaFunction(self.discovery_lambda)],
        )
        events.Rule(
            self,
            "MonthlyPentestScheduleRule",
            schedule=events.Schedule.cron(minute="0", hour="2", day="1", month="*"),
            targets=[
                targets.SfnStateMachine(
                    self.pentest_lifecycle,
                    # Le run planifie n'a pas d'identifiants d'application :
                    # le trigger suffit a distinguer les executions mensuelles.
                    input=events.RuleTargetInput.from_object({"trigger": "schedule"}),
                )
            ],
        )
