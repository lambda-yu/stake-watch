from pathlib import Path
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
