from pathlib import Path
from unittest.mock import MagicMock

import pytest
from stake_watch.main import build_app


@pytest.mark.asyncio
async def test_build_app_with_seed(tmp_path: Path):
    db_path = tmp_path / "test.db"
    seed_yaml = tmp_path / "seed.yaml"
    seed_yaml.write_text("""
wallets: []
rpc:
  base:
    primary: "https://mainnet.base.org"
intervals:
  positions: 300
risk:
  liquidation_warning: 1.3
protocols:
  - name: aave_v3_base
    chain: base
    collector: defillama
    defillama_slug: aave-v3
    enabled: true
""")
    runner, storage, settings = await build_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        seed_path=str(seed_yaml),
    )
    assert runner is not None
    assert len(runner.collectors) >= 1
    assert settings.intervals.positions == 300
    await storage.close()


@pytest.mark.asyncio
async def test_build_app_empty_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    runner, storage, settings = await build_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        seed_path="nonexistent.yaml",
    )
    assert runner is not None
    assert len(runner.collectors) == 0
    await storage.close()


@pytest.mark.asyncio
async def test_build_command_bot_returns_bot_when_config_present():
    from stake_watch.main import _build_command_bot
    storage = MagicMock()
    bot = _build_command_bot("fake-token", "42", storage)
    assert bot is not None
    assert bot._bot_token == "fake-token"
    assert bot._chat_id == 42


@pytest.mark.asyncio
async def test_build_command_bot_returns_none_when_token_missing():
    from stake_watch.main import _build_command_bot
    assert _build_command_bot(None, "42", MagicMock()) is None
    assert _build_command_bot("", "42", MagicMock()) is None


@pytest.mark.asyncio
async def test_build_command_bot_returns_none_when_chat_id_missing_or_invalid():
    from stake_watch.main import _build_command_bot
    assert _build_command_bot("t", None, MagicMock()) is None
    assert _build_command_bot("t", "abc", MagicMock()) is None
    assert _build_command_bot("t", "", MagicMock()) is None
