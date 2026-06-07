"""Unit tests for UniverseLoader."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest

from src.universe.loader import UniverseLoader


UNIVERSE_CSV = """\
symbol,company_name,sector,industry,isin,exchange,breeze_code,lot_size
RELIANCE,Reliance Industries,Energy,Oil & Gas,INE002A01018,NSE,RELIANCE,1
TCS,Tata Consultancy Services,IT,IT Services,INE467B01029,NSE,TCS,1
HDFCBANK,HDFC Bank,Financials,Banking,INE040A01034,NSE,HDFCBANK,1
INFY,Infosys,IT,IT Services,INE009A01021,NSE,INFY,1
"""


@pytest.fixture
def universe_csv(tmp_path: Path) -> str:
    f = tmp_path / "nifty500.csv"
    f.write_text(UNIVERSE_CSV)
    return str(f)


@pytest.fixture
def loader(universe_csv: str) -> UniverseLoader:
    return UniverseLoader(universe_csv)


class TestLoad:
    def test_loads_all_entries(self, loader):
        entries = loader.load()
        assert len(entries) == 4

    def test_entry_fields(self, loader):
        entries = loader.load()
        r = entries[0]
        assert r.symbol == "RELIANCE"
        assert r.sector == "Energy"
        assert r.exchange == "NSE"
        assert r.lot_size == 1

    def test_size_limit_truncates(self, universe_csv):
        l = UniverseLoader(universe_csv, size_limit=2)
        assert len(l.load()) == 2

    def test_cached_on_second_call(self, loader):
        entries1 = loader.load()
        entries2 = loader.load()
        assert entries1 is entries2  # same object (cached)

    def test_force_reload_returns_fresh_list(self, loader):
        entries1 = loader.load()
        entries2 = loader.load(force_reload=True)
        assert entries1 is not entries2  # new list

    def test_missing_file_raises(self, tmp_path):
        l = UniverseLoader(str(tmp_path / "missing.csv"))
        with pytest.raises(FileNotFoundError):
            l.load()

    def test_missing_required_column_raises(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text("symbol,company_name\nRELIANCE,Reliance\n")
        l = UniverseLoader(str(bad))
        with pytest.raises(ValueError, match="missing columns"):
            l.load()


class TestHelperMethods:
    def test_symbols_returns_list_of_strings(self, loader):
        syms = loader.symbols()
        assert isinstance(syms, list)
        assert "RELIANCE" in syms
        assert len(syms) == 4

    def test_sector_map_keys_match_symbols(self, loader):
        sm = loader.sector_map()
        assert sm["RELIANCE"] == "Energy"
        assert sm["TCS"] == "IT"

    def test_company_map(self, loader):
        cm = loader.company_map()
        assert cm["RELIANCE"] == "Reliance Industries"

    def test_get_entry_found(self, loader):
        entry = loader.get_entry("TCS")
        assert entry is not None
        assert entry.company_name == "Tata Consultancy Services"

    def test_get_entry_not_found(self, loader):
        assert loader.get_entry("NOTLISTED") is None

    def test_sectors_returns_sorted_unique(self, loader):
        secs = loader.sectors()
        assert secs == sorted(set(secs))
        assert "IT" in secs
        assert "Energy" in secs

    def test_by_sector_filters_correctly(self, loader):
        it_stocks = loader.by_sector("IT")
        assert all(e.sector == "IT" for e in it_stocks)
        assert len(it_stocks) == 2  # TCS + INFY

    def test_to_dataframe_returns_dataframe(self, loader):
        df = loader.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert "symbol" in df.columns
        assert "sector" in df.columns
        assert len(df) == 4
