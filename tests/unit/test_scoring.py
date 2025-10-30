"""Unit tests for weighted scoring logic."""

from src.models import DecisionType, LLMResponse
from src.scoring import WeightedScorer


def test_unanimous_yes_decision():
    """Test scoring when all LLMs say YES."""
    scorer = WeightedScorer({"claude": 1.0, "gemini": 1.0, "perplexity": 1.0})

    responses = [
        LLMResponse(
            provider="claude",
            decision=DecisionType.YES,
            confidence=0.9,
            reasoning="Test reasoning",
            raw_response="yes",
            error=None,
        ),
        LLMResponse(
            provider="gemini",
            decision=DecisionType.YES,
            confidence=0.85,
            reasoning="Test reasoning",
            raw_response="yes",
            error=None,
        ),
        LLMResponse(
            provider="perplexity",
            decision=DecisionType.YES,
            confidence=0.95,
            reasoning="Test reasoning",
            raw_response="yes",
            error=None,
        ),
    ]

    result = scorer.aggregate_responses("Test query", responses)

    assert result.final_decision == DecisionType.YES
    assert result.final_confidence > 0.8
    assert len(result.llm_responses) == 3


def test_weighted_decision():
    """Test scoring with different weights (higher weight wins)."""
    scorer = WeightedScorer({"claude": 2.0, "gemini": 1.0})

    responses = [
        LLMResponse(
            provider="claude",
            decision=DecisionType.YES,
            confidence=0.9,
            reasoning="Claude says yes",
            raw_response="yes",
            error=None,
        ),
        LLMResponse(
            provider="gemini",
            decision=DecisionType.NO,
            confidence=0.9,
            reasoning="Gemini says no",
            raw_response="no",
            error=None,
        ),
    ]

    result = scorer.aggregate_responses("Test query", responses)

    # Claude has 2x weight, so YES should win
    assert result.final_decision == DecisionType.YES


def test_uncertain_when_no_clear_winner():
    """Test that UNCERTAIN is returned when there's no clear consensus."""
    scorer = WeightedScorer({"claude": 1.0, "gemini": 1.0})

    responses = [
        LLMResponse(
            provider="claude",
            decision=DecisionType.YES,
            confidence=0.5,
            reasoning="Maybe yes",
            raw_response="uncertain",
            error=None,
        ),
        LLMResponse(
            provider="gemini",
            decision=DecisionType.NO,
            confidence=0.5,
            reasoning="Maybe no",
            raw_response="uncertain",
            error=None,
        ),
    ]

    result = scorer.aggregate_responses("Test query", responses)

    # Equal weights and low confidence should result in UNCERTAIN
    assert result.final_decision == DecisionType.UNCERTAIN


def test_handles_errors_gracefully():
    """Test that scoring handles LLM errors gracefully."""
    scorer = WeightedScorer({"claude": 1.0, "gemini": 1.0})

    responses = [
        LLMResponse(
            provider="claude",
            decision=DecisionType.YES,
            confidence=0.9,
            reasoning="Claude works",
            raw_response="yes",
            error=None,
        ),
        LLMResponse(
            provider="gemini",
            decision=DecisionType.UNCERTAIN,
            confidence=0.0,
            reasoning="Error occurred",
            raw_response="",
            error="API timeout",
        ),
    ]

    result = scorer.aggregate_responses("Test query", responses)

    # Should still produce a result even with one error
    assert result.final_decision in [DecisionType.YES, DecisionType.NO, DecisionType.UNCERTAIN]
    assert len(result.llm_responses) == 2
