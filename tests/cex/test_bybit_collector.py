import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from stake_watch.collectors.cex.bybit import BybitEarnCollector

FIX = json.loads((Path(__file__).parent / "fixtures/bybit_earn.json").read_text())


class _Resp:
    def __init__(self, body):
        self._b = body
    def raise_for_status(self):
        pass
    def json(self):
        return self._b


@pytest.mark.asyncio
async def test_bybit_parses_tiered_usdt():
    # Fixture contains only USDT; USDC request returns an empty list body.
    empty = {"retCode": 0, "result": {"list": []}}

    async def _get(url, **kw):
        if "coin=USDT" in url:
            return _Resp(FIX)
        return _Resp(empty)

    with patch("stake_watch.collectors.cex.bybit.httpx.AsyncClient") as MC:
        client = MC.return_value.__aenter__.return_value
        client.get = AsyncMock(side_effect=_get)
        rates = await BybitEarnCollector(["USDT", "USDC"]).fetch()

    assert len(rates) == 1
    r = rates[0]
    assert r.venue == "bybit" and r.asset == "USDT"
    # Fixture tiers: 6.52% and 1.52% → min=0.0152, max=0.0652
    assert r.apy_min == pytest.approx(0.0152, rel=1e-6)
    assert r.apy_max == pytest.approx(0.0652, rel=1e-6)
    assert r.tier_note and "6.52%" in r.tier_note and "1.52%" in r.tier_note