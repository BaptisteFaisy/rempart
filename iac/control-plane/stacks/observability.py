"""Observability stack — ENF-OBS-01 : traces, métriques et alarmes sur chaque étape.

Sans cette stack, une panne du plan de contrôle est invisible : les tests ne se
lancent plus, les failles ne sont plus triées, et personne ne le sait avant
qu'un client se plaigne. Chaque alarme correspond à un mode de panne précis du
parcours (chapitre 8), pas à un seuil décoratif.

Le tracing X-Ray est activé sur chaque fonction par `_helpers.create_python_lambda`.
"""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
import aws_cdk.aws_cloudwatch as cw
import aws_cdk.aws_cloudwatch_actions as cw_actions
import aws_cdk.aws_dynamodb as ddb
import aws_cdk.aws_lambda as _lambda
import aws_cdk.aws_sns as sns
from constructs import Construct

# ENF-PERF-01 : une page du portail doit répondre en moins de 2 secondes.
API_LATENCY_P95_MS = 2000
EVALUATION_PERIODS = 2
DATA_POINTS_TO_ALARM = 2


class ObservabilityStack(cdk.Stack):
    """Alarmes CloudWatch du plan de contrôle, routées vers un topic SNS."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_function: _lambda.IFunction,
        task_lambdas: dict[str, _lambda.IFunction],
        discovery_lambda: _lambda.IFunction,
        state_machines: dict[str, Any],
        tables: dict[str, ddb.ITable],
        alarm_topic: sns.ITopic | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.topic = alarm_topic or sns.Topic(
            self, "RempartAlarmTopic", display_name="Rempart operational alarms"
        )
        self.alarms: list[cw.Alarm] = []

        self._alarm_on_api(api_function)
        self._alarm_on_task_lambdas(task_lambdas, discovery_lambda)
        self._alarm_on_state_machines(state_machines)
        self._alarm_on_tables(tables)

    # ------------------------------------------------------------------ #
    # Alarmes
    # ------------------------------------------------------------------ #
    def _alarm_on_api(self, api_function: _lambda.IFunction) -> None:
        """L'API est la seule porte d'entrée du portail : lenteur et erreurs."""
        self._add(
            "ApiErrors",
            api_function.metric_errors(period=cdk.Duration.minutes(5), statistic="Sum"),
            threshold=1,
            description="API Lambda errors — the portal cannot serve a page.",
        )
        self._add(
            "ApiLatencyP95",
            api_function.metric_duration(
                period=cdk.Duration.minutes(5), statistic="p95"
            ),
            threshold=API_LATENCY_P95_MS,
            description="API p95 above the 2 s budget of ENF-PERF-01.",
        )
        self._add(
            "ApiThrottles",
            api_function.metric_throttles(period=cdk.Duration.minutes(5), statistic="Sum"),
            threshold=1,
            description="API concurrency throttled — raise the reserved concurrency.",
        )

    def _alarm_on_task_lambdas(
        self,
        task_lambdas: dict[str, _lambda.IFunction],
        discovery_lambda: _lambda.IFunction,
    ) -> None:
        """Une tâche d'orchestration en échec bloque tout le cycle de vie."""
        for name, function in sorted(task_lambdas.items()):
            self._add(
                f"Task{name.title().replace('_', '')}Errors",
                function.metric_errors(period=cdk.Duration.minutes(5), statistic="Sum"),
                threshold=1,
                description=f"Orchestrator task '{name}' is failing.",
            )
        self._add(
            "DiscoveryErrors",
            discovery_lambda.metric_errors(
                period=cdk.Duration.minutes(15), statistic="Sum"
            ),
            threshold=1,
            description="CI/CD run discovery failing: gate tests go unnoticed (EF-ORC-01).",
        )
        self._add(
            "DiscoveryInvocationsMissing",
            discovery_lambda.metric_invocations(
                period=cdk.Duration.minutes(30), statistic="Sum"
            ),
            threshold=1,
            comparison_operator=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            description="Discovery has not run in 30 min: the schedule is broken.",
        )

    def _alarm_on_state_machines(self, state_machines: dict[str, Any]) -> None:
        """Un run arrêté en route = un test payé mais jamais trié."""
        for name, machine in sorted(state_machines.items()):
            self._add(
                f"Sfn{name.title().replace('_', '')}Failed",
                cw.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionsFailed",
                    dimensions_map={"StateMachineArn": machine.state_machine_arn},
                    period=cdk.Duration.minutes(5),
                    statistic="Sum",
                ),
                threshold=1,
                description=f"Step Functions '{name}' executions are failing.",
            )

    def _alarm_on_tables(self, tables: dict[str, ddb.ITable]) -> None:
        """Le throttling DynamoDB ferait échouer l'API et l'orchestrateur."""
        for name, table in sorted(tables.items()):
            metric = cw.Metric(
                namespace="AWS/DynamoDB",
                metric_name="ThrottledRequests",
                dimensions_map={
                    "TableName": table.table_name,
                    "Operation": "PutItem",
                },
                period=cdk.Duration.minutes(5),
                statistic="Sum",
            )
            self._add(
                f"Table{name.title().replace('-', '')}Throttled",
                metric,
                threshold=1,
                description=f"DynamoDB table '{name}' is throttling writes.",
            )

    # ------------------------------------------------------------------ #
    # Helper
    # ------------------------------------------------------------------ #
    def _add(
        self,
        id_: str,
        metric: cw.IMetric,
        *,
        threshold: float,
        description: str,
        comparison_operator: cw.ComparisonOperator = (
            cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
        ),
    ) -> cw.Alarm:
        """Crée une alarme, la route vers le topic et la garde dans la liste."""
        alarm = cw.Alarm(
            self,
            id_,
            metric=metric,
            threshold=threshold,
            evaluation_periods=EVALUATION_PERIODS,
            datapoints_to_alarm=DATA_POINTS_TO_ALARM,
            comparison_operator=comparison_operator,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            alarm_description=description,
        )
        alarm.add_alarm_action(cw_actions.SnsAction(self.topic))
        self.alarms.append(alarm)
        return alarm
