import pytest
from stake_watch.collectors.cex.registry import build_cex_collector
from stake_watch.models.cex import CexVenue


def _v(name):
    return CexVenue(name=name, display_name=name.upper())


def test_all_five_resolve():
    for n in ("binance", "okx", "bybit", "gate", "bitget"):
        c = build_cex_collector(_v(n))
        assert c is not None and c.venue == n


def test_unknown_returns_none():
    assert build_cex_collector(_v("nonesuch")) is None