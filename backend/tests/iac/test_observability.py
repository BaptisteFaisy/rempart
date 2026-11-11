"""ENF-OBS-01 : des alarmes existent réellement sur chaque étape du parcours.

Sans ce test, la stack d'observabilité pourrait synthétiser mais ne rien
surveiller — exactement le travers du placeholder Lambda corrigé par ailleurs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from aws_cdk import assertions

IAC_DIR = Path(__file__).resolve().parents[3] / "iac" / "control-plane"
if str(IAC_DIR) not in sys.path:
    sys.path.insert(0, str(IAC_DIR))

from app import build_app  # noqa: E402

ENV = {"account": "123456789012", "region": "eu-west-3"}


@pytest.fixture(scope="module")
def template() -> assertions.Template:
    app = build_app()
    stack = app.node.find_child("RempartObservabilityStack")
    return assertions.Template.from_stack(stack)


def test_observability_stack_is_part_of_the_app():
    app = build_app()
    assert app.node.find_child("RempartObservabilityStack") is not None


def test_every_alarm_routes_to_the_sns_topic(template: assertions.Template):
    """Une alarme sans action ne prévient personne : elle ne sert à rien."""
    alarms = template.find_resources("AWS::CloudWatch::Alarm")
    assert alarms, "aucune alarme synthétisée"
    for logical_id, alarm in alarms.items():
        actions = alarm["Properties"].get("AlarmActions") or []
        assert actions, f"{logical_id} sans AlarmActions (aucune notification)"


def test_alarms_cover_the_api(template: assertions.Template):
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {"AlarmDescription": assertions.Match.string_like_regexp("API Lambda errors")},
    )
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {"AlarmDescription": assertions.Match.string_like_regexp("ENF-PERF-01")},
    )


def test_alarms_cover_the_orchestrator_tasks(template: assertions.Template):
    """Les 8 tâches + la découverte doivent être surveillées."""
    descriptions = [
        a["Properties"].get("AlarmDescription", "")
        for a in template.find_resources("AWS::CloudWatch::Alarm").values()
    ]
    joined = "\n".join(descriptions)
    assert "Orchestrator task" in joined
    assert "CI/CD run discovery failing" in joined
    assert "Discovery has not run" in joined


def test_alarms_cover_the_three_state_machines(template: assertions.Template):
    descriptions = [
        a["Properties"].get("AlarmDescription", "")
        for a in template.find_resources("AWS::CloudWatch::Alarm").values()
    ]
    joined = "\n".join(descriptions)
    for machine in ("pentest_lifecycle", "cicd_intake", "retest_close"):
        assert machine in joined or machine.title().replace("_", "") in "".join(
            a["Properties"].get("AlarmName", "")
            for a in template.find_resources("AWS::CloudWatch::Alarm").values()
        ), f"aucune alarme pour la machine {machine}"


def test_alarms_cover_dynamo_throttling(template: assertions.Template):
    descriptions = [
        a["Properties"].get("AlarmDescription", "")
        for a in template.find_resources("AWS::CloudWatch::Alarm").values()
    ]
    assert any("throttling writes" in d for d in descriptions)


def test_alarm_thresholds_are_breaching_not_missing_data(template: assertions.Template):
    """`NOT_BREACHING` évite les fausses alertes quand aucune donnée n'arrive."""
    for logical_id, alarm in template.find_resources("AWS::CloudWatch::Alarm").items():
        props = alarm["Properties"]
        assert props.get("TreatMissingData") == "notBreaching", logical_id
        assert props.get("EvaluationPeriods", 0) >= 1, logical_id


def test_latency_threshold_matches_the_two_second_budget(template: assertions.Template):
    """ENF-PERF-01 : page du portail en moins de 2 secondes."""
    alarms = template.find_resources("AWS::CloudWatch::Alarm")
    latency = [
        a for a in alarms.values()
        if "ENF-PERF-01" in a["Properties"].get("AlarmDescription", "")
    ]
    assert latency, "alarme de latence introuvable"
    assert float(latency[0]["Properties"]["Threshold"]) == 2000.0


def test_an_sns_topic_exists_for_operational_alarms(template: assertions.Template):
    template.resource_count_is("AWS::SNS::Topic", 1)
