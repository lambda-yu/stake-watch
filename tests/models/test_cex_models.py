from datetime import datetime, timezone
from stake_watch.models.cex import CexEarnRate, VenueRateSnapshot, CexVenue


def test_cex_earn_rate_defaults_product_type_and_max_equals_min():
    now = datetime.now(timezone.utc)
    r = CexEarnRate(venue="okx", asset="USDT", apy_min=0.04, apy_max=0.04, updated_at=now)
    assert r.product_type == "flexible"
    assert r.tier_note is None and r.raw_json is None


def test_cex_venue_defaults():
    v = CexVenue(name="binance", display_name="Binance")
    assert v.enabled is True and v.assets == ["USDT", "USDC"]


def test_snapshot_default_errors_empty():
    s = VenueRateSnapshot(venue="okx", rates=[])
    assert s.errors == []