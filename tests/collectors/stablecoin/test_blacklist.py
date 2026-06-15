from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.stablecoin.blacklist import BlacklistChecker

@pytest.mark.asyncio
async def test_not_blacklisted():
    checker = BlacklistChecker()
    mock_contract = MagicMock()
    mock_contract.functions.isBlacklisted.return_value.call = AsyncMock(return_value=False)
    with patch.object(checker, '_get_contract', return_value=mock_contract):
        result = await checker.check("0xWallet", "USDC", "ethereum", "https://fake")
    assert result.is_blacklisted is False

@pytest.mark.asyncio
async def test_blacklisted():
    checker = BlacklistChecker()
    mock_contract = MagicMock()
    mock_contract.functions.isBlacklisted.return_value.call = AsyncMock(return_value=True)
    with patch.object(checker, '_get_contract', return_value=mock_contract):
        result = await checker.check("0xWallet", "USDC", "ethereum", "https://fake")
    assert result.is_blacklisted is True
