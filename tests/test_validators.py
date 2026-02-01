"""Unit tests for validators module."""

from __future__ import annotations

import pytest

from thesis_check.validators import (
    AgentRole,
    SIMILARITY_THRESHOLD,
    SPEC_A,
    SPEC_B,
    parse_template,
    similarity,
    stop_phrase_hit,
    too_similar,
    truncate,
    validate_agent_output,
)


class TestTruncate:
    def test_no_truncation_needed(self) -> None:
        assert truncate("hello", 10) == "hello"

    def test_truncation_applied(self) -> None:
        assert truncate("hello world", 5) == "hello"

    def test_exact_length(self) -> None:
        assert truncate("hello", 5) == "hello"

    def test_empty_string(self) -> None:
        assert truncate("", 10) == ""


class TestStopPhraseHit:
    def test_phrase_found(self) -> None:
        assert stop_phrase_hit("Agreement reached, debate ends.", ["agreement reached"])

    def test_phrase_not_found(self) -> None:
        assert not stop_phrase_hit("The debate continues.", ["agreement reached"])

    def test_case_insensitive(self) -> None:
        assert stop_phrase_hit("AGREEMENT REACHED", ["agreement reached"])

    def test_empty_text(self) -> None:
        assert not stop_phrase_hit("", ["agreement reached"])

    def test_empty_phrases(self) -> None:
        assert not stop_phrase_hit("some text", [])


class TestSimilarity:
    def test_identical_strings(self) -> None:
        assert similarity("hello", "hello") == 1.0

    def test_completely_different(self) -> None:
        assert similarity("abc", "xyz") < 0.5

    def test_case_insensitive(self) -> None:
        assert similarity("Hello", "hello") == 1.0

    def test_empty_strings(self) -> None:
        assert similarity("", "") == 1.0


class TestParseTemplate:
    def test_valid_pro_template(self) -> None:
        text = (
            "- PRO1: First argument\n"
            "- PRO2: Second argument\n"
            "- NEW_ASSUMPTION: Some assumption\n"
            "- RISK: Some risk"
        )
        result = parse_template(text, SPEC_A)
        assert result is not None
        assert result["PRO1"] == "First argument"
        assert result["PRO2"] == "Second argument"
        assert result["NEW_ASSUMPTION"] == "Some assumption"
        assert result["RISK"] == "Some risk"

    def test_valid_contra_template(self) -> None:
        text = (
            "- CONTRA1: First counter\n"
            "- CONTRA2: Second counter\n"
            "- ASSUMPTION_CHECK: Checking assumption\n"
            "- EDGE_CASE: Edge case example"
        )
        result = parse_template(text, SPEC_B)
        assert result is not None
        assert result["CONTRA1"] == "First counter"

    def test_wrong_number_of_lines(self) -> None:
        text = "- PRO1: Only one line"
        assert parse_template(text, SPEC_A) is None

    def test_missing_dash_prefix(self) -> None:
        text = (
            "PRO1: First argument\n"
            "- PRO2: Second argument\n"
            "- NEW_ASSUMPTION: Some assumption\n"
            "- RISK: Some risk"
        )
        assert parse_template(text, SPEC_A) is None

    def test_missing_colon(self) -> None:
        text = (
            "- PRO1 First argument\n"
            "- PRO2: Second argument\n"
            "- NEW_ASSUMPTION: Some assumption\n"
            "- RISK: Some risk"
        )
        assert parse_template(text, SPEC_A) is None

    def test_duplicate_keys(self) -> None:
        text = (
            "- PRO1: First argument\n"
            "- PRO1: Duplicate\n"
            "- NEW_ASSUMPTION: Some assumption\n"
            "- RISK: Some risk"
        )
        assert parse_template(text, SPEC_A) is None

    def test_wrong_keys(self) -> None:
        text = (
            "- WRONG1: First argument\n"
            "- WRONG2: Second argument\n"
            "- WRONG3: Some assumption\n"
            "- WRONG4: Some risk"
        )
        assert parse_template(text, SPEC_A) is None


class TestValidateAgentOutput:
    def test_valid_pro_output(self) -> None:
        text = (
            "- PRO1: First argument\n"
            "- PRO2: Second argument\n"
            "- NEW_ASSUMPTION: Some assumption\n"
            "- RISK: Some risk"
        )
        assert validate_agent_output(text, AgentRole.PRO) is True
        assert validate_agent_output(text, "A") is True

    def test_valid_contra_output(self) -> None:
        text = (
            "- CONTRA1: First counter\n"
            "- CONTRA2: Second counter\n"
            "- ASSUMPTION_CHECK: Checking assumption\n"
            "- EDGE_CASE: Edge case example"
        )
        assert validate_agent_output(text, AgentRole.CONTRA) is True
        assert validate_agent_output(text, "B") is True

    def test_pro_template_fails_contra_validation(self) -> None:
        text = (
            "- PRO1: First argument\n"
            "- PRO2: Second argument\n"
            "- NEW_ASSUMPTION: Some assumption\n"
            "- RISK: Some risk"
        )
        assert validate_agent_output(text, AgentRole.CONTRA) is False


class TestTooSimilar:
    def test_identical_is_similar(self) -> None:
        assert too_similar("hello world", "hello world") is True

    def test_different_is_not_similar(self) -> None:
        assert too_similar("completely different text", "other unrelated words") is False

    def test_empty_previous_not_similar(self) -> None:
        assert too_similar("some text", "") is False
        assert too_similar("some text", "   ") is False

    def test_threshold_boundary(self) -> None:
        # Default threshold is 0.92
        assert SIMILARITY_THRESHOLD == 0.92


class TestAgentRole:
    def test_pro_value(self) -> None:
        assert AgentRole.PRO.value == "A"

    def test_contra_value(self) -> None:
        assert AgentRole.CONTRA.value == "B"

    def test_from_string(self) -> None:
        assert AgentRole("A") == AgentRole.PRO
        assert AgentRole("B") == AgentRole.CONTRA
