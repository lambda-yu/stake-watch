from datetime import datetime, timezone
from decimal import Decimal

from stake_watch.alerts.stablecoin_report import format_stablecoin_report
from stake_watch.models.stablecoin import StablecoinRiskSnapshot


def test_format_empty():
    text = format_stablecoin_report([])
    assert "暂无数据" in text


def test_format_with_data():
    snaps = [
        StablecoinRiskSnapshot(
            token="USDC", price=0.9998, deviation=0.0002,
            total_supply=Decimal("75000000000"), supply_change_24h_pct=0.67,
            supply_change_7d_pct=2.74, risk_level="safe", risk_score=5.2,
            updated_at=datetime.now(timezone.utc)),
        StablecoinRiskSnapshot(
            token="USDT", price=0.994, deviation=0.006,
            total_supply=Decimal("186000000000"), supply_change_24h_pct=-3.5,
            supply_change_7d_pct=-5.0, risk_level="caution", risk_score=42.0,
            cex_spread_pct=0.35,
            updated_at=datetime.now(timezone.utc)),
    ]
    text = format_stablecoin_report(snaps)
    assert "USDC" in text
    assert "USDT" in text
    assert "安全" in text
    assert "注意" in text
    assert "$0.9998" in text
    assert "$0.9940" in text
    assert "75.0B" in text
    assert "186.0B" in text
    assert "+0.67%" in text
    assert "-3.50%" in text
    assert "0.350%" in text  # CEX spread
    assert "采集:" in text  # Collection timestamp


def test_format_hard_trigger():
    snap = StablecoinRiskSnapshot(
        token="USDT", price=0.975, deviation=0.025,
        total_supply=Decimal("186000000000"), supply_change_24h_pct=-5.0,
        supply_change_7d_pct=-8.0, risk_level="critical", risk_score=100,
        hard_trigger="price_below_098",
        updated_at=datetime.now(timezone.utc))
    text = format_stablecoin_report([snap])
    assert "硬触发" in text
    assert "严重" in text
