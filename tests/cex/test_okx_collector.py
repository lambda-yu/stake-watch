import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from stake_watch.collectors.cex.okx import OkxEarnCollector

FIX = json.loads((Path(__file__).parent / "fixtures/okx_earn.json").read_text())


class _Resp:
    def __init__(self, body):
        self._b = body
    def raise_for_status(self):
        pass
    def json(self):
        return self._b


@pytest.mark.asyncio
async def test_okx_parses_usdt_and_usdc():
    async def _get(url, **kw):
        if "USDT" in url:
            return _Resp(FIX["USDT"])
        if "USDC" in url:
            return _Resp(FIX["USDC"])
        raise AssertionError(url)

    with patch("stake_watch.collectors.cex.okx.httpx.AsyncClient") as MC:
        client = MC.return_value.__aenter__.return_value
        client.get = AsyncMock(side_effect=_get)
        rates = await OkxEarnCollector(["USDT", "USDC"]).fetch()

    assets = {r.asset for r in rates}
    assert assets == {"USDT", "USDC"}
    for r in rates:
        assert r.apy_min == r.apy_max == 0.025  # single-rate, untiered
        assert r.product_type == "flexible" and r.venue == "okx"
        assert r.tier_note is None