import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from stake_watch.collectors.cex.gate import GateEarnCollector, HOURS_PER_YEAR

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
async def test_gate_annualizes_hourly_rates():
    # Fixture is USDT-only; USDC path returns 404 and is silently skipped
    async def _get(url, **kw):
        if "USDT" in url:
            return _Resp(FIX)
        return _Resp({}, code=404)

    with patch("stake_watch.collectors.cex.gate.httpx.AsyncClient") as MC:
        client = MC.return_value.__aenter__.return_value
        client.get = AsyncMock(side_effect=_get)
        rates = await GateEarnCollector(["USDT", "USDC"]).fetch()

    assert len(rates) == 1
    r = rates[0]
    assert r.venue == "gate" and r.asset == "USDT"
    # Fixture: min_rate=0.00000011 max_rate=0.00057 (hourly)
    assert r.apy_min == pytest.approx(0.00000011 * HOURS_PER_YEAR, rel=1e-6)
    assert r.apy_max == pytest.approx(0.00057 * HOURS_PER_YEAR, rel=1e-6)
    assert r.tier_note and "hourly" in r.tier_note