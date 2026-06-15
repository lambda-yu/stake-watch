import os
from pathlib import Path
import pytest
from stake_watch.config import AppSettings, ProtocolEntry, load_settings, load_protocols

@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text("""
wallets:
  - chain: base
    address: "0xTestWallet"
rpc:
  base:
    primary: "https://mainnet.base.org"
    fallback: []
database:
  url: "sqlite:///test.db"
intervals:
  positions: 300
  protocol_stats: 900
  stablecoin_price: 60
  stablecoin_supply: 600
  reserves: 21600
""")
    protocols_yaml = tmp_path / "protocols.yaml"
    protocols_yaml.write_text("""
protocols:
  - name: aave_v3_base
    chain: base
    collector: base_chain.aave_base
    enabled: true
    safety_score: 8.8
    primary_risks:
      - "shared pool bad debt"
""")
    return tmp_path

def test_load_settings(config_dir: Path):
    settings = load_settings(config_dir / "settings.yaml")
    assert len(settings.wallets) == 1
    assert settings.wallets[0].chain == "base"
    assert settings.wallets[0].address == "0xTestWallet"
    assert settings.rpc["base"].primary == "https://mainnet.base.org"
    assert settings.database.url == "sqlite:///test.db"
    assert settings.intervals.positions == 300

def test_load_protocols(config_dir: Path):
    protocols = load_protocols(config_dir / "protocols.yaml")
    assert len(protocols) == 1
    assert protocols[0].name == "aave_v3_base"
    assert protocols[0].chain == "base"
    assert protocols[0].enabled is True
    assert protocols[0].safety_score == 8.8

def test_settings_has_defaults():
    settings = load_settings(None)
    assert settings.intervals.positions == 300
    assert settings.intervals.protocol_stats == 900

def test_local_override(config_dir: Path):
    local = config_dir / "settings.local.yaml"
    local.write_text("""
wallets:
  - chain: ethereum
    address: "0xRealWallet"
""")
    settings = load_settings(config_dir / "settings.yaml", local_path=local)
    assert settings.wallets[0].chain == "ethereum"
    assert settings.wallets[0].address == "0xRealWallet"
