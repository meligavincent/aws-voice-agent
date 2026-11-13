from unittest.mock import Mock

import pytest

from voice_agent.ai import Unavailable
from voice_agent.cli import event
from voice_agent.service import Agent


def test_private_status_is_deterministic_and_never_sent_to_model(store):
    faq = Mock()
    result = Agent(store, faq).handle(event())
    assert "constat signé" in result["messages"][0]["content"]
    assert result["sessionState"]["intent"]["slots"]["AccessCode"] is None
    faq.answer.assert_not_called()


@pytest.mark.parametrize("code", ["111111", "000000"])
def test_wrong_credentials_cannot_read_claim_or_call_model(store, code):
    faq = Mock()
    result = Agent(store, faq).handle(event(code=code))
    assert result["sessionState"]["sessionAttributes"]["handoff"] == "true"
    assert "constat" not in result["messages"][0]["content"]
    faq.answer.assert_not_called()


def test_confirmation_is_required_and_duplicate_delivery_creates_one_ticket(store):
    agent = Agent(store, Mock())
    first = event("RequestCallback", session="same-session")
    assert agent.handle(first)["sessionState"]["dialogAction"]["type"] == "ConfirmIntent"
    assert list(store.pending()) == []
    first["sessionState"]["intent"]["confirmationState"] = "Confirmed"
    agent.handle(first)
    agent.handle(first)
    pending = list(store.pending())
    assert len(pending) == 1
    operation = pending[0]["operation_id"]
    store.complete_callback(operation)
    store.complete_callback(operation)
    assert store.get(f"TASK#{operation}")["status"] == "OPEN"
    assert list(store.pending()) == []


def test_decline_has_no_side_effect(store):
    result = Agent(store, Mock()).handle(event("RequestCallback", confirmation="Denied"))
    assert "pas été créée" in result["messages"][0]["content"]
    assert list(store.pending()) == []


def test_rate_limit_applies_across_sessions(store):
    for _ in range(12):
        assert store.authenticate("123456", "111111") is None
    assert store.authenticate("123456", "654321") is None


def test_missing_claim_has_same_public_failure(store):
    request = event()
    request["sessionState"]["intent"]["slots"]["ClaimNumber"]["value"]["interpretedValue"] = (
        "999999"
    )
    agent = Agent(store, Mock())
    assert agent.handle(request)["messages"] == agent.handle(event(code="111111"))["messages"]


@pytest.mark.parametrize(
    "question", ["mon dossier est-il payé ?", "my claim is 123456", "mon code est secret"]
)
def test_personal_question_cannot_use_faq(store, question):
    faq = Mock()
    request = event("FallbackIntent")
    request["inputTranscript"] = question
    assert (
        Agent(store, faq).handle(request)["sessionState"]["sessionAttributes"]["handoff"] == "true"
    )
    faq.answer.assert_not_called()


def test_bedrock_outage_routes_to_human(store):
    faq = Mock()
    faq.answer.side_effect = Unavailable()
    request = event("FallbackIntent")
    request["inputTranscript"] = "Quels sont vos horaires ?"
    assert (
        Agent(store, faq).handle(request)["sessionState"]["sessionAttributes"]["handoff"] == "true"
    )


def test_invalid_slot_is_cleared_for_reprompt(store):
    request = event(code="not-digits")
    result = Agent(store, Mock()).handle(request)
    assert result["sessionState"]["dialogAction"]["slotToElicit"] == "AccessCode"
    assert result["sessionState"]["intent"]["slots"]["AccessCode"] is None


def test_english_status(store):
    assert (
        "signed incident report"
        in Agent(store, Mock()).handle(event(locale="en_GB"))["messages"][0]["content"]
    )


def test_handoff_has_no_undeclared_slots(store):
    request = event("Handoff")
    request["sessionState"]["intent"]["slots"] = {}
    assert Agent(store, Mock()).handle(request)["sessionState"]["intent"]["slots"] == {}
