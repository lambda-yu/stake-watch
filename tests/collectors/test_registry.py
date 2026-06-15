from stake_watch.collectors.registry import build_collector
from stake_watch.config import ProtocolEntry
from stake_watch.collectors.defillama import DefiLlamaCollector
from stake_watch.collectors.aave.collector import AaveV3Collector
from stake_watch.collectors.compound.collector import CompoundV3Collector
from stake_watch.collectors.sky.collector import SkySusdsCollector
from stake_watch.collectors.morpho.collector import MorphoCollector
from stake_watch.collectors.kamino.collector import KaminoCollector

def test_build_defillama():
    e = ProtocolEntry(name="venus_usdc", chain="bsc", collector="defillama", defillama_slug="venus-core-pool")
    c = build_collector(e, rpc_urls={"bsc": "https://bsc-rpc"})
    assert isinstance(c, DefiLlamaCollector)

def test_build_aave():
    e = ProtocolEntry(name="aave_v3_base", chain="base", collector="aave_v3")
    c = build_collector(e, rpc_urls={"base": "https://base-rpc"})
    assert isinstance(c, AaveV3Collector)

def test_build_compound():
    e = ProtocolEntry(name="compound_v3_usdc", chain="base", collector="compound_v3")
    c = build_collector(e, rpc_urls={"base": "https://base-rpc"})
    assert isinstance(c, CompoundV3Collector)

def test_build_sky():
    e = ProtocolEntry(name="sky_susds", chain="ethereum", collector="sky_susds")
    c = build_collector(e, rpc_urls={"ethereum": "https://eth-rpc"})
    assert isinstance(c, SkySusdsCollector)

def test_build_morpho():
    e = ProtocolEntry(name="morpho_steakhouse_usdc", chain="base", collector="morpho", vault_address="0xBEEF")
    c = build_collector(e, rpc_urls={"base": "https://base-rpc"})
    assert isinstance(c, MorphoCollector)

def test_build_kamino():
    e = ProtocolEntry(name="kamino_usdc", chain="solana", collector="kamino")
    c = build_collector(e, rpc_urls={"solana": "https://sol-rpc"})
    assert isinstance(c, KaminoCollector)

def test_unknown_returns_none():
    e = ProtocolEntry(name="unknown", chain="base", collector="nonexistent")
    assert build_collector(e, rpc_urls={}) is None

def test_morpho_without_vault_returns_none():
    e = ProtocolEntry(name="morpho_test", chain="base", collector="morpho")
    assert build_collector(e, rpc_urls={"base": "https://rpc"}) is None
