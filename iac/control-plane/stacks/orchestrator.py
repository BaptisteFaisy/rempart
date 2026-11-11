"""Step Functions orchestrator stack for Rempart."""

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

from ._helpers import DEFAULT_TABLE_PREFIX, create_python_lambda

TASK_NAMES = (
    "budget_gate",
    "start_run",
    "poll_run",
    "collect_findings",
    "dispatch_triage",
    "create_tickets",
)


class OrchestratorStack(cdk.Stack):
    """Provisions Step Functions state machine and associated Lambdas."""

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
        self.lambdas = {
            name: self._create_task_lambda(name, common_env, tables) for name in TASK_NAMES
        }
        self.state_machine = self._build_state_machine()
        self.discovery_lambda = self._create_task_lambda(
            "discovery",
            common_env,
            tables,
            handler="rempart.orchestrator.discovery.lambda_handler",
        )
        self._setup_eventbridge_rules()

    def _create_task_lambda(
        self,
        name: str,
        env: dict[str, str],
        tables: dict[str, ddb.ITable],
        handler: str | None = None,
    ) -> _lambda.Function:
        fn = create_python_lambda(
            self,
            f"Lambda{name.title().replace('_', '')}",
            handler=handler or f"rempart.orchestrator.tasks.{name}",
            environment=env,
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

    def _invoke(self, step_id: str, lambda_key: str) -> tasks.LambdaInvoke:
        return tasks.LambdaInvoke(
            self,
            step_id,
            lambda_function=self.lambdas[lambda_key],
            output_path="$.Payload",
        )

    def _build_state_machine(self) -> sfn.StateMachine:
        t_budget_gate = self._invoke("BudgetGateTask", "budget_gate")
        t_start_run = self._invoke("StartRunTask", "start_run")
        t_wait = sfn.Wait(self, "Wait60s", time=sfn.WaitTime.duration(cdk.Duration.seconds(60)))
        t_poll_run = self._invoke("PollRunTask", "poll_run")
        t_collect = self._invoke("CollectFindingsTask", "collect_findings")
        t_triage = self._invoke("DispatchTriageTask", "dispatch_triage")
        t_tickets = self._invoke("CreateTicketsTask", "create_tickets")

        t_collect.next(t_triage).next(t_tickets).next(sfn.Succeed(self, "RunCompleted"))
        t_wait.next(t_poll_run).next(self._build_poll_choice(t_collect, t_wait))
        t_start_run.next(t_wait)
        t_budget_gate.next(self._build_gate_choice(t_start_run))

        return sfn.StateMachine(
            self,
            "RempartOrchestratorStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(t_budget_gate),
            timeout=cdk.Duration.hours(4),
        )

    def _build_poll_choice(self, t_collect: sfn.IChainable, t_wait: sfn.IChainable) -> sfn.Choice:
        failed_cond = sfn.Condition.or_(
            sfn.Condition.string_equals("$.status", "failed"),
            sfn.Condition.string_equals("$.status", "stopped"),
        )
        return (
            sfn.Choice(self, "IsRunFinished")
            .when(sfn.Condition.string_equals("$.status", "completed"), t_collect)
            .when(failed_cond, sfn.Fail(self, "PentestFailed", cause="Pentest failed or stopped"))
            .otherwise(t_wait)
        )

    def _build_gate_choice(self, t_start_run: sfn.IChainable) -> sfn.Choice:
        fail_budget = sfn.Fail(
            self,
            "BudgetOrMandateBlocked",
            cause="Budget exhausted or mandate missing/expired",
            error="BudgetGateFailed",
        )
        return (
            sfn.Choice(self, "IsBudgetAllowed")
            .when(sfn.Condition.boolean_equals("$.allowed", True), t_start_run)
            .otherwise(fail_budget)
        )

    def _setup_eventbridge_rules(self) -> None:
        events.Rule(
            self,
            "DiscoveryEvery5MinRule",
            schedule=events.Schedule.rate(cdk.Duration.minutes(5)),
            targets=[targets.LambdaFunction(self.discovery_lambda)],
        )
        events.Rule(
            self,
            "MonthlyFreezeRule",
            schedule=events.Schedule.cron(minute="0", hour="2", day="1", month="*"),
            targets=[targets.LambdaFunction(self.discovery_lambda)],
        )
