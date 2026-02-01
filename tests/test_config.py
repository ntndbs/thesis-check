"""Unit tests for config module."""

from __future__ import annotations

import pytest

from thesis_check.config import Settings


class TestSettingsValidation:
    def _make_settings(self, **overrides) -> Settings:
        """Create a Settings instance with defaults and optional overrides."""
        defaults = {
            "base_url": "http://localhost:1234/v1",
            "api_key": "test-key",
            "model_creative": "test-model",
            "model_critical": "test-model",
            "model_judge": "test-model",
            "temp_a": 0.8,
            "temp_b": 0.2,
            "temp_j": 0.0,
            "max_rounds": 3,
            "convergence_delta": 0.02,
            "stop_phrases": ["agreement reached"],
            "max_chars_agent": 700,
            "max_chars_judge": 2500,
            "seed": None,
            "log_dir": "runs",
        }
        defaults.update(overrides)
        return Settings(**defaults)

    def test_valid_settings(self) -> None:
        settings = self._make_settings()
        settings.validate()  # Should not raise

    def test_invalid_max_rounds(self) -> None:
        settings = self._make_settings(max_rounds=0)
        with pytest.raises(ValueError, match="max_rounds must be >= 1"):
            settings.validate()

    def test_invalid_convergence_delta(self) -> None:
        settings = self._make_settings(convergence_delta=0)
        with pytest.raises(ValueError, match="convergence_delta must be > 0"):
            settings.validate()

    def test_invalid_temp_a_high(self) -> None:
        settings = self._make_settings(temp_a=2.5)
        with pytest.raises(ValueError, match="temp_a must be in"):
            settings.validate()

    def test_invalid_temp_a_negative(self) -> None:
        settings = self._make_settings(temp_a=-0.1)
        with pytest.raises(ValueError, match="temp_a must be in"):
            settings.validate()

    def test_invalid_max_chars_agent(self) -> None:
        settings = self._make_settings(max_chars_agent=50)
        with pytest.raises(ValueError, match="max_chars_agent must be >= 100"):
            settings.validate()

    def test_empty_base_url(self) -> None:
        settings = self._make_settings(base_url="")
        with pytest.raises(ValueError, match="base_url cannot be empty"):
            settings.validate()

    def test_multiple_errors(self) -> None:
        settings = self._make_settings(max_rounds=0, temp_a=5.0)
        with pytest.raises(ValueError) as exc_info:
            settings.validate()
        assert "max_rounds" in str(exc_info.value)
        assert "temp_a" in str(exc_info.value)
