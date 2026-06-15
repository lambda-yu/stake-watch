from datetime import datetime, timezone
from decimal import Decimal
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position

def test_position_creation():
    pos = Position(chain=Chain.BASE, protocol="aave_v3_base", wallet="0xTest", asset="USDC",
        position_type=PositionType.SUPPLY, amount=Decimal("10000.00"), value_usd=Decimal("10000.00"),
        apy=3.17, updated_at=datetime.now(timezone.utc))
    assert pos.chain == Chain.BASE
    assert pos.position_type == PositionType.SUPPLY
    assert pos.amount == Decimal("10000.00")

def test_position_with_vault():
    pos = Position(chain=Chain.BASE, protocol="morpho_steakhouse_usdc", wallet="0xTest", asset="USDC",
        position_type=PositionType.VAULT, amount=Decimal("5000.00"), value_usd=Decimal("5000.00"),
        apy=3.8, vault_version="v1.1", updated_at=datetime.now(timezone.utc))
    assert pos.vault_version == "v1.1"
    assert pos.position_type == PositionType.VAULT
