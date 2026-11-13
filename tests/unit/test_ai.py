from unittest.mock import Mock

import pytest

from voice_agent.ai import PublicFAQ, Unavailable
from voice_agent.config import Settings


@pytest.fixture
def faq():
    session = Mock()
    instance = PublicFAQ(
        session,
        Settings(
            environment="aws",
            ai_mode="bedrock",
            model_id="model",
            knowledge_base_id="kb",
            guardrail_id="guard",
            guardrail_version="1",
        ),
        clock=lambda: 100.0,
    )
    instance.retrieval = Mock()
    instance.runtime = Mock()
    instance.retrieval.retrieve.return_value = {
        "retrievalResults": [{"score": 0.9, "content": {"text": "Open 9 to 5."}}]
    }
    instance.runtime.converse.return_value = {
        "stopReason": "end_turn",
        "output": {"message": {"content": [{"text": "Open 9 to 5."}]}},
    }
    return instance


def test_guardrail_version_and_token_budget_are_sent(faq):
    assert faq.answer("Opening hours?") == "Open 9 to 5."
    args = faq.runtime.converse.call_args.kwargs
    assert args["guardrailConfig"]["guardrailVersion"] == "1"
    assert args["inferenceConfig"]["maxTokens"] == 250
    assert "Open 9 to 5." in args["messages"][0]["content"][0]["text"]


def test_low_retrieval_score_never_invokes_generation(faq):
    faq.retrieval.retrieve.return_value = {
        "retrievalResults": [{"score": 0.1, "content": {"text": "unreliable"}}]
    }
    with pytest.raises(Unavailable):
        faq.answer("hours?")
    faq.runtime.converse.assert_not_called()


def test_guardrail_block_is_not_spoken_as_a_success(faq):
    faq.runtime.converse.return_value = {"stopReason": "guardrail_intervened"}
    with pytest.raises(Unavailable):
        faq.answer("unsafe request")


def test_circuit_opens_after_three_failures_and_recovers(faq):
    faq.retrieval.retrieve.side_effect = TimeoutError
    for _ in range(4):
        with pytest.raises(Unavailable):
            faq.answer("hours?")
    assert faq.retrieval.retrieve.call_count == 3
    faq.clock = lambda: 131.0
    faq.retrieval.retrieve.side_effect = None
    assert faq.answer("hours?")
    assert faq.failures == 0
