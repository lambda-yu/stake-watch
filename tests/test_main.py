from pathlib import Path
import pytest
from stake_watch.main import build_app

@pytest.mark.asyncio
async def test_build_app_returns_runner(tmp_path: Path):
    db_path = tmp_path / "test.db"
    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text(f"""
wallets:
  - chain: base
    address: "0xTest"
rpc:
  base:
    primary: "https://mainnet.base.org"
database:
  url: "sqlite+aiosqlite:///{db_path}"
""")
    protocols_yaml = tmp_path / "protocols.yaml"
    protocols_yaml.write_text("""
protocols:
  - name: aave_v3_base
    chain: base
    collector: defillama
    defillama_slug: aave-v3
    enabled: true
""")
    runner, storage, settings = await build_app(settings_path=settings_yaml, protocols_path=protocols_yaml)
    assert runner is not None
    assert len(runner.collectors) >= 1
    await storage.close()
