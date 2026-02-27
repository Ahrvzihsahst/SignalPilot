"""Instrument manager for Nifty 500 universe with Angel One token mappings."""

import csv
import logging
from pathlib import Path

import httpx

from signalpilot.db.models import Instrument
from signalpilot.utils.retry import with_retry

logger = logging.getLogger("signalpilot.data.instruments")

ANGEL_ONE_SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)


class InstrumentManager:
    """Manages the Nifty 500 instrument list and Angel One token mappings."""

    def __init__(self, nifty500_csv_path: str = "data/nifty500_list.csv") -> None:
        self._csv_path = nifty500_csv_path
        self._instruments: dict[str, Instrument] = {}
        self._token_map: dict[str, str] = {}

    async def load(self) -> None:
        """Load Nifty 500 list from CSV, fetch Angel One instrument master,
        cross-reference to build token mappings.

        Logs warnings for any symbols not found in instrument master.
        """
        csv_symbols = self._load_csv()
        angel_master = await self._fetch_instrument_master()

        # Filter for NSE equity instruments (symbol ends with -EQ)
        nse_equities: dict[str, dict] = {}
        for item in angel_master:
            if item.get("exch_seg") == "NSE" and item.get("symbol", "").endswith("-EQ"):
                # Extract base symbol: "SBIN-EQ" -> "SBIN"
                base_symbol = item["symbol"].rsplit("-EQ", 1)[0]
                nse_equities[base_symbol] = item

        # Cross-reference CSV symbols with instrument master
        for symbol_info in csv_symbols:
            symbol = symbol_info["symbol"]
            name = symbol_info.get("name", symbol)

            if symbol not in nse_equities:
                logger.warning("Symbol %s not found in Angel One instrument master, skipping", symbol)
                continue

            master = nse_equities[symbol]
            instrument = Instrument(
                symbol=symbol,
                name=name,
                angel_token=master["token"],
                exchange="NSE",
                nse_symbol=master["symbol"],
                yfinance_symbol=f"{symbol}.NS",
            )
            self._instruments[symbol] = instrument
            self._token_map[master["token"]] = symbol

        logger.info(
            "Loaded %d instruments from %d CSV symbols",
            len(self._instruments),
            len(csv_symbols),
        )

    def _load_csv(self) -> list[dict[str, str]]:
        """Read symbols from the Nifty 500 CSV file."""
        path = Path(self._csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Nifty 500 CSV not found: {self._csv_path}")

        symbols = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Support both "Symbol" and "symbol" column headers
                symbol = row.get("Symbol") or row.get("symbol")
                name = row.get("Company Name") or row.get("name") or symbol
                if symbol:
                    symbols.append({"symbol": symbol.strip(), "name": name.strip()})
        return symbols

    @with_retry(max_retries=3, base_delay=5.0, exceptions=(httpx.HTTPError,))
    async def _fetch_instrument_master(self) -> list[dict]:
        """Fetch Angel One instrument master JSON. Retries up to 3 times."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(ANGEL_ONE_SCRIP_MASTER_URL)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError(f"Expected list from instrument master, got {type(data)}")
            return data

    def get_all_tokens(self) -> list[dict]:
        """Return token list in the format required for WebSocket subscription.

        Returns list of dicts: [{"exchangeType": 1, "tokens": ["token1", ...]}, ...]
        """
        tokens = list(self._token_map.keys())
        return [{"exchangeType": 1, "tokens": tokens}]

    def get_symbol_by_token(self, token: str) -> str | None:
        """Look up symbol from Angel One token."""
        return self._token_map.get(token)

    def get_instrument(self, symbol: str) -> Instrument | None:
        """Get full instrument details by symbol."""
        return self._instruments.get(symbol)

    @property
    def symbols(self) -> list[str]:
        """All loaded Nifty 500 symbols."""
        return list(self._instruments.keys())
