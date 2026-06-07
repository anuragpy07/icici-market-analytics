"""Universe management — loads and filters the Nifty 500 stock list."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {"symbol", "company_name", "sector"}


@dataclass(frozen=True)
class UniverseEntry:
    """Immutable record for a single universe member."""

    symbol: str
    company_name: str
    sector: str
    industry: str
    isin: str
    exchange: str
    breeze_code: str
    lot_size: int


class UniverseLoader:
    """Loads, validates, and caches the equity universe from a CSV file.

    The universe is a static snapshot updated by the exchange periodically.
    For live reconstitution (additions/deletions), a scheduled job would
    refresh this file from NSE's website.
    """

    def __init__(self, universe_file: str, size_limit: int = 0) -> None:
        self._file = universe_file
        self._size_limit = size_limit
        self._entries: Optional[list[UniverseEntry]] = None

    def load(self, force_reload: bool = False) -> list[UniverseEntry]:
        """Return the full universe, loading from disk if not yet cached."""
        if self._entries is not None and not force_reload:
            return self._entries

        try:
            df = pd.read_csv(self._file)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Universe file not found: {self._file}. "
                "Ensure data/universe/nifty500.csv exists."
            ) from exc

        missing = _REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"Universe CSV missing columns: {missing}")

        # Fill optional columns with sensible defaults
        df["industry"] = df.get("industry", "Unknown").fillna("Unknown")
        df["isin"] = df.get("isin", "").fillna("")
        df["exchange"] = df.get("exchange", "NSE").fillna("NSE")
        df["breeze_code"] = df.get("breeze_code", df["symbol"]).fillna(df["symbol"])
        df["lot_size"] = df.get("lot_size", 1).fillna(1).astype(int)

        # Apply size limit (useful for fast integration tests)
        if self._size_limit and self._size_limit > 0:
            df = df.head(self._size_limit)
            logger.info("Universe size limited to %d symbols", self._size_limit)

        self._entries = [
            UniverseEntry(
                symbol=str(row["symbol"]).strip(),
                company_name=str(row["company_name"]).strip(),
                sector=str(row["sector"]).strip(),
                industry=str(row["industry"]).strip(),
                isin=str(row["isin"]).strip(),
                exchange=str(row["exchange"]).strip(),
                breeze_code=str(row["breeze_code"]).strip(),
                lot_size=int(row["lot_size"]),
            )
            for _, row in df.iterrows()
        ]

        logger.info("Universe loaded: %d symbols from %s", len(self._entries), self._file)
        return self._entries

    def symbols(self) -> list[str]:
        return [e.symbol for e in self.load()]

    def sector_map(self) -> dict[str, str]:
        return {e.symbol: e.sector for e in self.load()}

    def company_map(self) -> dict[str, str]:
        return {e.symbol: e.company_name for e in self.load()}

    def get_entry(self, symbol: str) -> Optional[UniverseEntry]:
        for entry in self.load():
            if entry.symbol == symbol:
                return entry
        return None

    def sectors(self) -> list[str]:
        return sorted({e.sector for e in self.load()})

    def by_sector(self, sector: str) -> list[UniverseEntry]:
        return [e for e in self.load() if e.sector == sector]

    def to_dataframe(self) -> pd.DataFrame:
        entries = self.load()
        return pd.DataFrame(
            [
                {
                    "symbol": e.symbol,
                    "company_name": e.company_name,
                    "sector": e.sector,
                    "industry": e.industry,
                    "isin": e.isin,
                    "exchange": e.exchange,
                    "breeze_code": e.breeze_code,
                }
                for e in entries
            ]
        )
