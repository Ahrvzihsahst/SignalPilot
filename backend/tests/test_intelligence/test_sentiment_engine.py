"""Tests for the VADER and FinBERT sentiment engines."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from signalpilot.intelligence.sentiment_engine import (
    ScoredHeadline,
    SentimentEngine,
    VADERSentimentEngine,
)

# Path to the real financial lexicon bundled with the package
_LEXICON_PATH = str(
    Path(__file__).resolve().parents[2]
    / "signalpilot"
    / "intelligence"
    / "financial_lexicon.json"
)


class TestVADERSentimentEngine:
    """Tests for the VADER sentiment engine."""

    def test_positive_headline(self):
        """Positive headline should yield a positive compound score."""
        engine = VADERSentimentEngine()
        result = engine.analyze("Company reports excellent earnings and strong growth and profit surge")
        assert isinstance(result, ScoredHeadline)
        assert result.compound_score > 0.0
        assert result.model_used == "vader"
        assert result.positive_score > 0.0

    def test_negative_headline(self):
        """Negative headline should yield a negative compound score."""
        engine = VADERSentimentEngine()
        result = engine.analyze("SEBI investigation into fraud at major company")
        assert isinstance(result, ScoredHeadline)
        assert result.compound_score < 0.0
        assert result.negative_score > 0.0

    def test_neutral_headline(self):
        """Neutral headline should yield a near-zero compound score."""
        engine = VADERSentimentEngine()
        result = engine.analyze("Company holds annual general meeting")
        assert isinstance(result, ScoredHeadline)
        # VADER compound for truly neutral text is close to zero
        assert -0.5 < result.compound_score < 0.5

    def test_financial_lexicon_overlay_strengthens_scores(self):
        """Financial lexicon overlay should make domain-specific terms more impactful."""
        engine_without = VADERSentimentEngine()
        engine_with = VADERSentimentEngine(lexicon_path=_LEXICON_PATH)

        text = "SEBI probe reveals major issues at company"
        score_without = engine_without.analyze(text).compound_score
        score_with = engine_with.analyze(text).compound_score

        # The lexicon assigns "SEBI probe" a score of -3.5 which should make
        # the overall score more negative
        assert score_with <= score_without

    def test_missing_lexicon_file_fallback(self):
        """Missing lexicon file should not raise; engine uses default VADER."""
        engine = VADERSentimentEngine(lexicon_path="/nonexistent/path/lexicon.json")
        result = engine.analyze("Company reports excellent earnings and strong growth")
        assert isinstance(result, ScoredHeadline)
        assert result.compound_score > 0.0

    def test_malformed_lexicon_fallback(self):
        """Malformed lexicon JSON should not raise; engine uses default VADER."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json content!!!")
            f.flush()
            tmp_path = f.name
        try:
            engine = VADERSentimentEngine(lexicon_path=tmp_path)
            result = engine.analyze("Company reports excellent earnings and strong growth")
            assert isinstance(result, ScoredHeadline)
            assert result.compound_score > 0.0
        finally:
            os.unlink(tmp_path)

    def test_non_dict_lexicon_fallback(self):
        """Lexicon file that is valid JSON but not a dict should be skipped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([1, 2, 3], f)
            f.flush()
            tmp_path = f.name
        try:
            engine = VADERSentimentEngine(lexicon_path=tmp_path)
            result = engine.analyze("Company reports excellent earnings and strong growth")
            assert isinstance(result, ScoredHeadline)
            assert result.compound_score > 0.0
        finally:
            os.unlink(tmp_path)

    def test_analyze_batch_returns_correct_count(self):
        """analyze_batch should return one ScoredHeadline per input text."""
        engine = VADERSentimentEngine()
        texts = [
            "Company reports excellent earnings and strong growth",
            "SEBI investigation into fraud",
            "Company holds annual meeting",
        ]
        results = engine.analyze_batch(texts)
        assert len(results) == 3
        assert all(isinstance(r, ScoredHeadline) for r in results)
        assert results[0].title == texts[0]
        assert results[1].title == texts[1]
        assert results[2].title == texts[2]

    def test_analyze_batch_empty_list(self):
        """analyze_batch with empty list should return empty list."""
        engine = VADERSentimentEngine()
        results = engine.analyze_batch([])
        assert results == []

    def test_scored_headline_fields(self):
        """ScoredHeadline should carry all expected fields."""
        engine = VADERSentimentEngine()
        result = engine.analyze("Test headline")
        assert result.title == "Test headline"
        assert result.source == ""
        assert result.published_at is None
        assert result.model_used == "vader"
        # All score fields should be floats
        assert isinstance(result.positive_score, float)
        assert isinstance(result.negative_score, float)
        assert isinstance(result.neutral_score, float)
        assert isinstance(result.compound_score, float)

    def test_model_name_property(self):
        """model_name should return 'vader'."""
        engine = VADERSentimentEngine()
        assert engine.model_name == "vader"


class TestSentimentEngineProtocol:
    """Tests to verify protocol compliance."""

    def test_vader_satisfies_protocol(self):
        """VADERSentimentEngine should satisfy the SentimentEngine protocol."""
        engine = VADERSentimentEngine()
        assert isinstance(engine, SentimentEngine)

    def test_protocol_has_required_methods(self):
        """SentimentEngine protocol should require model_name, analyze, and analyze_batch."""
        # Check protocol attributes exist
        assert hasattr(SentimentEngine, "model_name")
        assert hasattr(SentimentEngine, "analyze")
        assert hasattr(SentimentEngine, "analyze_batch")


class TestFinancialLexiconFile:
    """Tests for the financial_lexicon.json file itself."""

    def test_lexicon_file_is_valid_json(self):
        """The financial lexicon JSON file should parse successfully."""
        with open(_LEXICON_PATH) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_lexicon_contains_expected_terms(self):
        """Lexicon should contain key Indian market terms."""
        with open(_LEXICON_PATH) as f:
            data = json.load(f)
        assert "SEBI probe" in data
        assert "fraud" in data
        assert "record revenue" in data
        assert "earnings beat" in data
        assert "buyback" in data

    def test_lexicon_values_are_numeric(self):
        """All lexicon values should be numeric."""
        with open(_LEXICON_PATH) as f:
            data = json.load(f)
        for term, score in data.items():
            assert isinstance(score, (int, float)), f"Non-numeric score for '{term}': {score}"

    def test_lexicon_has_positive_and_negative_terms(self):
        """Lexicon should contain both positive and negative sentiment terms."""
        with open(_LEXICON_PATH) as f:
            data = json.load(f)
        positives = [v for v in data.values() if v > 0]
        negatives = [v for v in data.values() if v < 0]
        assert len(positives) > 0, "Lexicon has no positive terms"
        assert len(negatives) > 0, "Lexicon has no negative terms"
