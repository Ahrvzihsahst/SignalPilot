"""Morning Brief Generator for pre-market Telegram message."""

from __future__ import annotations

import logging
from datetime import datetime

from signalpilot.intelligence.regime_data import PreMarketData
from signalpilot.utils.constants import IST

logger = logging.getLogger(__name__)


class MorningBriefGenerator:
    """Generate the pre-market morning brief Telegram message.

    Combines global cues (S&P 500, Nasdaq, Asian markets, SGX Nifty),
    India context (VIX, FII/DII), regime prediction, and watchlist alerts.
    """

    def __init__(self, data_collector, watchlist_repo, config) -> None:
        self._data_collector = data_collector  # RegimeDataCollector
        self._watchlist_repo = watchlist_repo  # WatchlistRepository
        self._config = config  # AppConfig
        self._last_brief: str | None = None

    async def generate(self) -> str:
        """Generate the morning brief message."""
        data = await self._data_collector.collect_pre_market_data()

        regime_prediction, reasoning = self._predict_regime(data)

        watchlist_entries = []
        try:
            if self._watchlist_repo:
                watchlist_entries = await self._watchlist_repo.get_active_entries()
        except Exception:
            logger.warning("Failed to fetch watchlist for morning brief")

        brief = self._format_brief(data, regime_prediction, reasoning, watchlist_entries)
        self._last_brief = brief
        return brief

    def get_cached_brief(self) -> str | None:
        """Return the cached morning brief for the MORNING command."""
        return self._last_brief

    def _predict_regime(self, data: PreMarketData) -> tuple[str, str]:
        """Predict likely regime from pre-market data."""
        reasons = []
        regime_signals = {"TRENDING": 0, "RANGING": 0, "VOLATILE": 0}

        if data.india_vix is not None:
            if data.india_vix >= 22:
                regime_signals["VOLATILE"] += 2
                reasons.append(f"VIX elevated at {data.india_vix:.1f}")
            elif data.india_vix >= 18:
                regime_signals["VOLATILE"] += 1
                reasons.append(f"VIX moderately high at {data.india_vix:.1f}")
            elif data.india_vix < 12:
                regime_signals["RANGING"] += 1
                reasons.append(f"VIX low at {data.india_vix:.1f}")
            else:
                reasons.append(f"VIX normal at {data.india_vix:.1f}")

        if data.sgx_direction is not None:
            if data.sgx_direction in ("UP", "DOWN"):
                regime_signals["TRENDING"] += 1
                reasons.append(f"SGX Nifty pointing {data.sgx_direction}")
            else:
                regime_signals["RANGING"] += 1
                reasons.append("SGX Nifty flat")

        if data.sp500_change_pct is not None:
            if abs(data.sp500_change_pct) > 1.0:
                regime_signals["TRENDING"] += 1
                reasons.append(f"S&P 500 moved {data.sp500_change_pct:+.1f}%")
            elif abs(data.sp500_change_pct) < 0.3:
                regime_signals["RANGING"] += 1
                reasons.append(f"S&P 500 flat at {data.sp500_change_pct:+.1f}%")

        if not reasons:
            return "UNKNOWN", "Insufficient pre-market data"

        predicted = max(regime_signals, key=regime_signals.get)
        if max(regime_signals.values()) == 0:
            predicted = "TRENDING"

        return predicted, "; ".join(reasons)

    def _format_brief(
        self,
        data: PreMarketData,
        regime_prediction: str,
        reasoning: str,
        watchlist_entries: list,
    ) -> str:
        """Format the morning brief into the Telegram message."""
        now = datetime.now(IST)
        lines = [
            "\u2501" * 22,
            "<b>SIGNALPILOT \u2014 MORNING BRIEF</b>",
            now.strftime("%A, %d %B %Y"),
            "\u2501" * 22,
            "",
            "<b>GLOBAL CUES</b>",
        ]

        sp = _fmt_pct(data.sp500_change_pct)
        nq = _fmt_pct(data.nasdaq_change_pct)
        lines.append(f"  S&P 500: {sp} | Nasdaq: {nq}")
        nk = _fmt_pct(data.nikkei_change_pct)
        hs = _fmt_pct(data.hang_seng_change_pct)
        lines.append(f"  Nikkei: {nk} | Hang Seng: {hs}")
        sgx_str = f"{data.sgx_direction or 'N/A'}"
        if data.sgx_change_pct is not None:
            sgx_str += f" ({data.sgx_change_pct:+.1f}%)"
        lines.append(f"  SGX Nifty: {sgx_str}")

        lines.append("")
        lines.append("<b>INDIA CONTEXT</b>")

        vix_str = f"{data.india_vix:.1f}" if data.india_vix is not None else "N/A"
        vix_interp = _vix_interpretation(data.india_vix)
        lines.append(f"  India VIX: {vix_str} ({vix_interp})")
        lines.append(f"  FII (yesterday): {_fmt_crores(data.fii_net_crores)}")
        lines.append(f"  DII (yesterday): {_fmt_crores(data.dii_net_crores)}")

        lines.append("")
        lines.append(f"<b>REGIME PREDICTION: Likely {regime_prediction} DAY</b>")
        lines.append(f"  {reasoning}")

        if watchlist_entries:
            lines.append("")
            lines.append("<b>WATCHLIST ALERTS</b>")
            for entry in watchlist_entries[:5]:
                symbol = getattr(entry, "symbol", str(entry))
                lines.append(f"  {symbol}")

        lines.append("")
        lines.append("\u2501" * 22)
        lines.append("Classification at 9:30 AM. First signals expected 9:30-9:45 AM.")

        return "\n".join(lines)


def _fmt_pct(value: float | None) -> str:
    """Format a percentage value."""
    if value is None:
        return "N/A"
    return f"{value:+.1f}%"


def _fmt_crores(value: float | None) -> str:
    """Format a crore value."""
    if value is None:
        return "N/A"
    return f"{value:+,.0f} Cr"


def _vix_interpretation(vix: float | None) -> str:
    """Return a human-readable VIX interpretation."""
    if vix is None:
        return "unavailable"
    if vix < 12:
        return "very calm"
    if vix < 14:
        return "normal"
    if vix < 18:
        return "slightly elevated"
    if vix < 22:
        return "high"
    return "very high - defensive mode"
