"""Sentiment engine protocol and implementations (VADER + FinBERT)."""
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class ScoredHeadline:
    """Sentiment scores for a single headline."""
    title: str
    source: str
    published_at: datetime | None
    positive_score: float
    negative_score: float
    neutral_score: float
    compound_score: float
    model_used: str


@runtime_checkable
class SentimentEngine(Protocol):
    """Protocol for sentiment analysis engines."""

    @property
    def model_name(self) -> str: ...

    def analyze(self, text: str) -> ScoredHeadline: ...

    def analyze_batch(self, texts: list[str]) -> list[ScoredHeadline]: ...


class VADERSentimentEngine:
    """VADER-based sentiment engine with optional financial lexicon overlay."""

    def __init__(self, lexicon_path: str | None = None) -> None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        self._analyzer = SentimentIntensityAnalyzer()
        if lexicon_path:
            self._load_financial_lexicon(lexicon_path)

    @property
    def model_name(self) -> str:
        return "vader"

    def analyze(self, text: str) -> ScoredHeadline:
        scores = self._analyzer.polarity_scores(text)
        return ScoredHeadline(
            title=text,
            source="",
            published_at=None,
            positive_score=scores["pos"],
            negative_score=scores["neg"],
            neutral_score=scores["neu"],
            compound_score=scores["compound"],
            model_used="vader",
        )

    def analyze_batch(self, texts: list[str]) -> list[ScoredHeadline]:
        return [self.analyze(text) for text in texts]

    def _load_financial_lexicon(self, path: str) -> None:
        """Load and merge financial lexicon into VADER's lexicon dict."""
        try:
            with open(path) as f:
                lexicon = json.load(f)
            if isinstance(lexicon, dict):
                self._analyzer.lexicon.update(lexicon)
                logger.info("Loaded %d financial lexicon terms from %s", len(lexicon), path)
            else:
                logger.warning("Financial lexicon at %s is not a dict, skipping", path)
        except FileNotFoundError:
            logger.warning("Financial lexicon not found at %s, using default VADER", path)
        except json.JSONDecodeError:
            logger.warning("Malformed JSON in financial lexicon at %s, using default VADER", path)


class FinBERTSentimentEngine:
    """FinBERT-based sentiment engine (requires transformers + torch)."""

    def __init__(self) -> None:
        try:
            from transformers import pipeline
            self._pipeline = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                return_all_scores=True,
            )
        except ImportError:
            raise ImportError(
                "FinBERT requires 'transformers' and 'torch'. "
                "Install with: pip install transformers torch sentencepiece"
            )

    @property
    def model_name(self) -> str:
        return "finbert"

    def analyze(self, text: str) -> ScoredHeadline:
        results = self._pipeline(text[:512])  # FinBERT max 512 tokens
        scores = {r["label"]: r["score"] for r in results[0]}
        pos = scores.get("positive", 0.0)
        neg = scores.get("negative", 0.0)
        neu = scores.get("neutral", 0.0)
        compound = pos - neg  # Simple compound approximation
        return ScoredHeadline(
            title=text,
            source="",
            published_at=None,
            positive_score=pos,
            negative_score=neg,
            neutral_score=neu,
            compound_score=compound,
            model_used="finbert",
        )

    def analyze_batch(self, texts: list[str]) -> list[ScoredHeadline]:
        return [self.analyze(text) for text in texts]
