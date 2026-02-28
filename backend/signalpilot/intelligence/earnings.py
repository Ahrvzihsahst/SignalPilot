"""Earnings calendar management -- CSV ingestion and Screener.in scraping."""
import csv
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


class EarningsCalendar:
    """Manages earnings date ingestion from multiple sources."""

    def __init__(self, earnings_repo, config) -> None:
        self._earnings_repo = earnings_repo
        self._config = config

    async def ingest_from_csv(self, csv_path: str | None = None) -> int:
        """Parse CSV and upsert earnings dates. Return count upserted."""
        path = csv_path or self._config.news_earnings_csv_path
        try:
            p = Path(path)
            if not p.exists():
                logger.warning("Earnings CSV not found at %s", path)
                return 0
            count = 0
            with open(p) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        stock_code = row["stock_code"].strip()
                        earnings_date = date.fromisoformat(row["earnings_date"].strip())
                        quarter = row.get("quarter", "").strip()
                        is_confirmed = row.get("is_confirmed", "false").strip().lower() in (
                            "true", "1", "yes"
                        )
                        await self._earnings_repo.upsert_earnings(
                            stock_code=stock_code,
                            earnings_date=earnings_date,
                            quarter=quarter,
                            source="csv",
                            is_confirmed=is_confirmed,
                        )
                        count += 1
                    except (KeyError, ValueError) as e:
                        logger.warning("Skipping invalid earnings CSV row: %s", e)
            logger.info("Ingested %d earnings entries from CSV", count)
            return count
        except Exception:
            logger.warning("Failed to ingest earnings CSV from %s", path, exc_info=True)
            return 0

    async def ingest_from_screener(self) -> int:
        """Scrape Screener.in for upcoming earnings dates."""
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(
                    "https://www.screener.in/api/company/earnings_calendar/"
                ) as resp:
                    if resp.status != 200:
                        logger.warning("Screener.in returned status %d", resp.status)
                        return 0
                    data = await resp.json()
                    count = 0
                    for entry in data if isinstance(data, list) else []:
                        try:
                            stock_code = entry.get("symbol", "").strip()
                            earnings_date = date.fromisoformat(entry.get("date", ""))
                            quarter = entry.get("quarter", "")
                            await self._earnings_repo.upsert_earnings(
                                stock_code=stock_code,
                                earnings_date=earnings_date,
                                quarter=quarter,
                                source="screener.in",
                                is_confirmed=True,
                            )
                            count += 1
                        except (KeyError, ValueError):
                            continue
                    logger.info("Ingested %d earnings from Screener.in", count)
                    return count
        except Exception:
            logger.warning("Failed to scrape Screener.in earnings", exc_info=True)
            return 0

    async def refresh(self) -> int:
        """Run all configured ingestion sources. Return total upserted."""
        total = 0
        total += await self.ingest_from_csv()
        total += await self.ingest_from_screener()
        logger.info("Earnings calendar refresh complete: %d total entries", total)
        return total
