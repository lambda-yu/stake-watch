from datetime import datetime, timezone
from decimal import Decimal
from stake_watch.models.stablecoin import StablecoinPrice, StablecoinSupply, ChainSupply, StablecoinRiskSnapshot

def test_stablecoin_price():
    p = StablecoinPrice(token="USDC", price=0.9998, deviation=0.0002,
        price_24h_change=-0.01, source="coingecko", updated_at=datetime.now(timezone.utc))
    assert p.deviation < 0.01

def test_stablecoin_supply():
    s = StablecoinSupply(token="USDC", total_circulating=Decimal("75000000000"),
        chain_breakdown=[ChainSupply(chain="Ethereum", circulating=Decimal("48000000000"),
            prev_day=Decimal("47500000000"), change_24h_pct=1.05)],
        net_change_24h=Decimal("500000000"), net_change_24h_pct=0.67,
        net_change_7d_pct=2.74, updated_at=datetime.now(timezone.utc))
    assert s.net_change_24h_pct > 0

def test_risk_snapshot():
    r = StablecoinRiskSnapshot(token="USDT", price=0.994, deviation=0.006,
        total_supply=Decimal("186000000000"), supply_change_24h_pct=-3.2,
        supply_change_7d_pct=-5.1, risk_level="danger", updated_at=datetime.now(timezone.utc))
    assert r.risk_level == "danger"
