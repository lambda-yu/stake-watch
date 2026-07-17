import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from stake_watch.collectors.cex.gate import GateEarnCollector

FIX = json.loads((Path(__file__).parent / "fixtures/gate_earn.json").read_text())


class _Resp:
    def __init__(self, body, code=200):
        self._b = body
        self.status_code = code
    def raise_for_status(self):
        pass
    def json(self):
        return self._b


@pytest.mark.asyncio
async def test_gate_reads_est_rate_per_currency():
    async def _get(url, **kw):
        return _Resp(FIX)

    with patch("stake_watch.collectors.cex.gate.httpx.AsyncClient") as MC:
        client = MC.return_value.__aenter__.return_value
        client.get = AsyncMock(side_effect=_get)
        rates = await GateEarnCollector(["USDT", "USDC"]).fetch()

    by_asset = {r.asset: r for r in rates}
    assert set(by_asset.keys()) == {"USDT", "USDC"}
    # USDT est_rate = 0.0161 → 1.61% APR (already decimal, no conversion)
    assert by_asset["USDT"].apy_min == by_asset["USDT"].apy_max == pytest.approx(0.0161)
    assert by_asset["USDC"].apy_min == by_asset["USDC"].apy_max == pytest.approx(0.0118)
    for r in rates:
        assert r.venue == "gate" and r.product_type == "flexible"
        assert r.tier_note is None  # untiered