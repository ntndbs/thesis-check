"""Unit tests for runner module."""

from __future__ import annotations

import json

import pytest

from thesis_check.runner import JudgeOut, parse_judge


class TestParseJudge:
    def test_valid_json(self) -> None:
        raw = json.dumps({
            "summary": "Test summary",
            "key_evidence_for": ["point1", "point2"],
            "key_evidence_against": ["counter1"],
            "verdict": "In favor",
            "probability": 0.7,
        })
        result = parse_judge(raw)
        assert result.summary == "Test summary"
        assert result.key_evidence_for == ["point1", "point2"]
        assert result.key_evidence_against == ["counter1"]
        assert result.verdict == "In favor"
        assert result.probability == 0.7

    def test_json_with_extra_text(self) -> None:
        raw = 'Here is my response: {"summary":"test","key_evidence_for":[],"key_evidence_against":[],"verdict":"ok","probability":0.5} end'
        result = parse_judge(raw)
        assert result.summary == "test"
        assert result.verdict == "ok"
        assert result.probability == 0.5

    def test_probability_clamped_high(self) -> None:
        raw = json.dumps({
            "summary": "test",
            "probability": 1.5,
        })
        result = parse_judge(raw)
        assert result.probability == 1.0

    def test_probability_clamped_low(self) -> None:
        raw = json.dumps({
            "summary": "test",
            "probability": -0.5,
        })
        result = parse_judge(raw)
        assert result.probability == 0.0

    def test_missing_fields_use_defaults(self) -> None:
        raw = json.dumps({"summary": "minimal"})
        result = parse_judge(raw)
        assert result.summary == "minimal"
        assert result.key_evidence_for == []
        assert result.key_evidence_against == []
        assert result.verdict == ""
        assert result.probability == 0.5

    def test_invalid_json_fallback(self) -> None:
        raw = "This is not JSON at all"
        result = parse_judge(raw)
        assert result.summary == "JSON-Fallback"
        assert result.probability == 0.5
        assert "This is not JSON" in result.verdict

    def test_empty_string(self) -> None:
        result = parse_judge("")
        assert result.summary == "JSON-Fallback"

    def test_none_input(self) -> None:
        result = parse_judge(None)  # type: ignore
        assert result.summary == "JSON-Fallback"

    def test_evidence_list_truncated(self) -> None:
        raw = json.dumps({
            "summary": "test",
            "key_evidence_for": [f"point{i}" for i in range(20)],
            "key_evidence_against": [],
            "verdict": "ok",
            "probability": 0.5,
        })
        result = parse_judge(raw)
        assert len(result.key_evidence_for) == 10


class TestJudgeOut:
    def test_dataclass_fields(self) -> None:
        j = JudgeOut(
            summary="sum",
            key_evidence_for=["a"],
            key_evidence_against=["b"],
            verdict="v",
            probability=0.6,
        )
        assert j.summary == "sum"
        assert j.probability == 0.6
