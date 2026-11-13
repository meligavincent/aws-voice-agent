import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from voice_agent.ai import Unavailable
from voice_agent.cli import event
from voice_agent.service import Agent

CASES = json.loads(Path("evals/policy_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_versioned_conversation_policy(store, case):
    faq = Mock()
    faq.answer.side_effect = Unavailable()
    request = event(case["intent"], code=case["code"], locale=case["locale"])
    request["inputTranscript"] = case.get("question", "")
    result = Agent(store, faq).handle(request)
    assert case["contains"] in result["messages"][0]["content"]
    assert (result["sessionState"]["sessionAttributes"]["handoff"] == "true") == case["handoff"]


def test_flow_has_no_dangling_transitions_and_closes_on_unavailable():
    raw = Path("infra/modules/regional/templates/flow.json.tftpl").read_text()
    flow = json.loads(raw.replace("${alias_arn}", "alias").replace("${queue_arn}", "queue"))
    actions = {action["Identifier"]: action for action in flow["Actions"]}
    assert flow["StartAction"] in actions
    for action in actions.values():
        transitions = action["Transitions"]
        targets = [transitions["NextAction"]] if "NextAction" in transitions else []
        targets += [
            item["NextAction"]
            for kind in ("Errors", "Conditions")
            for item in transitions.get(kind, [])
        ]
        assert all(target in actions for target in targets)
    assert actions["unavailable"]["Transitions"]["NextAction"] == "end"
    assert actions["hours"]["Transitions"]["Conditions"][0]["Condition"]["Operands"] == ["True"]


def test_lex_has_both_locales_obfuscated_access_codes_and_no_logs():
    template = json.loads(Path("infra/modules/regional/templates/voice.json").read_text())
    locales = template["Resources"]["Bot"]["Properties"]["BotLocales"]
    assert {loc["LocaleId"] for loc in locales} == {"fr_FR", "en_GB"}
    assert "ConversationLogSettings" not in template["Resources"]["Alias"]["Properties"]
    for loc in locales:
        for intent in loc["Intents"]:
            for slot in intent.get("Slots", []):
                if slot["Name"] == "AccessCode":
                    assert (
                        slot["ObfuscationSetting"]["ObfuscationSettingType"] == "DefaultObfuscation"
                    )
