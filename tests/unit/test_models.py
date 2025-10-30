"""Unit tests for Pydantic model validation."""

import pytest
from pydantic import ValidationError

from src.models import OracleQuery


def test_valid_query():
    """Test that valid queries pass validation."""
    query = OracleQuery(query="Did the Lakers win the 2020 NBA Championship?")
    assert query.query == "Did the Lakers win the 2020 NBA Championship?"


def test_query_too_short():
    """Test that queries under 10 characters are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        OracleQuery(query="Too short")

    assert "at least 10 characters" in str(exc_info.value)


def test_query_too_long():
    """Test that queries over 256 characters are rejected."""
    long_query = "a" * 257
    with pytest.raises(ValidationError) as exc_info:
        OracleQuery(query=long_query)

    assert "at most 256 characters" in str(exc_info.value)


def test_query_with_special_characters():
    """Test that allowed special characters pass validation."""
    valid_queries = [
        "What is 2+2? Is it 4?",
        "Did team A/B win?",
        "Question with $100 amount",
        "Question with 50% probability",
        "Question with #hashtag",
        "Question with @mention",
        "Question with & ampersand",
    ]

    for q in valid_queries:
        query = OracleQuery(query=q)
        assert query.query == q


def test_query_rejects_invalid_characters():
    """Test that invalid characters are rejected."""
    invalid_queries = [
        "Query with < bracket",
        "Query with > bracket",
        "Query with [square] brackets",
        "Query with {curly} braces",
        "Query with | pipe",
        "Query with \\ backslash",
    ]

    for q in invalid_queries:
        with pytest.raises(ValidationError):
            OracleQuery(query=q)


def test_query_minimum_length_boundary():
    """Test exact minimum length (10 characters)."""
    # Exactly 10 characters should pass
    query = OracleQuery(query="1234567890")
    assert len(query.query) == 10

    # 9 characters should fail
    with pytest.raises(ValidationError):
        OracleQuery(query="123456789")


def test_query_maximum_length_boundary():
    """Test exact maximum length (256 characters)."""
    # Exactly 256 characters should pass
    query_256 = "a" * 256
    query = OracleQuery(query=query_256)
    assert len(query.query) == 256

    # 257 characters should fail
    query_257 = "a" * 257
    with pytest.raises(ValidationError):
        OracleQuery(query=query_257)
