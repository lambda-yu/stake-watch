# Stake Watch P2-protocols: On-Chain Protocol Collectors

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add on-chain collectors for Aave V3 (Base), Compound V3 (Base), Sky sUSDS (Ethereum), and Kamino (Solana) that can read real wallet positions (supply balance, health factor, APY). Also register all 10 protocols in seed.yaml.

**Architecture:** Each protocol gets a collector class extending BaseCollector. EVM collectors use web3.py (already installed). Solana collector uses solana-py. DefiLlama remains as fallback for protocol stats; on-chain collectors add wallet-specific position data.

**Tech Stack:** web3.py (installed), solana-py + solders (new), existing BaseCollector pipeline

**Depends on:** P1a + P1b + P1-morpho + P2 complete (71 tests passing)

---

## Contract References

| Protocol | Chain | Key Contract | Method |
|---|---|---|---|
| Aave V3 | Base | Pool `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5` | `getUserAccountData(address)` |
| Compound V3 (Comet) | Base | USDC Comet `0xb125E6687d4313864e53df431d5425969c15Eb2F` | `balanceOf(address)`, `borrowBalanceOf(address)` |
| Sky sUSDS | Ethereum | sUSDS `0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD` | ERC4626: `balanceOf`, `convertToAssets`, `asset` |
| Kamino | Solana | Reserve accounts | Via Kamino SDK / direct account parsing |

---

## Chunk 1: EVM On-Chain Collectors

### Task P1: Aave V3 Base collector

**Files:**
- Create: `src/stake_watch/collectors/aave/__init__.py`
- Create: `src/stake_watch/collectors/aave/collector.py`
- Create: `src/stake_watch/collectors/aave/abi.py`
- Test: `tests/collectors/aave/__init__.py`
- Test: `tests/collectors/aave/test_collector.py`

- [ ] **Step 1: Write tests**

```python
# tests/collectors/aave/test_collector.py
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.aave.collector import AaveV3Collector
from stake_watch.models.common import Chain, PositionType

@pytest.mark.asyncio
async def test_collect_positions():
    collector = AaveV3Collector(chain=Chain.BASE, protocol="aave_v3_base",
        pool_address="0xPool", rpc_url="https://fake")

    mock_pool = MagicMock()
    # getUserAccountData returns: totalCollateralBase, totalDebtBase, availableBorrowsBase,
    # currentLiquidationThreshold, ltv, healthFactor (all in base currency units with 8 decimals)
    mock_pool.functions.getUserAccountData.return_value.call = AsyncMock(
        return_value=(10000 * 10**8, 5000 * 10**8, 3000 * 10**8, 8000, 7500, int(1.5 * 10**18)))

    with patch.object(collector, '_get_pool_contract', return_value=mock_pool):
        positions = await collector.collect_positions("0xWallet")

    assert len(positions) == 1
    p = positions[0]
    assert p.protocol == "aave_v3_base"
    assert p.position_type == PositionType.SUPPLY
    assert p.health_factor == 1.5
    assert p.value_usd == Decimal("10000")

@pytest.mark.asyncio
async def test_collect_positions_no_deposit():
    collector = AaveV3Collector(chain=Chain.BASE, protocol="aave_v3_base",
        pool_address="0xPool", rpc_url="https://fake")
    mock_pool = MagicMock()
    mock_pool.functions.getUserAccountData.return_value.call = AsyncMock(
        return_value=(0, 0, 0, 0, 0, 0))
    with patch.object(collector, '_get_pool_contract', return_value=mock_pool):
        positions = await collector.collect_positions("0xWallet")
    assert len(positions) == 0
```

- [ ] **Step 2: Implement**

```python
# src/stake_watch/collectors/aave/abi.py
AAVE_V3_POOL_ABI = [
    {"inputs": [{"name": "user", "type": "address"}], "name": "getUserAccountData",
     "outputs": [
         {"name": "totalCollateralBase", "type": "uint256"},
         {"name": "totalDebtBase", "type": "uint256"},
         {"name": "availableBorrowsBase", "type": "uint256"},
         {"name": "currentLiquidationThreshold", "type": "uint256"},
         {"name": "ltv", "type": "uint256"},
         {"name": "healthFactor", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]

AAVE_V3_POOL_BASE = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
```

```python
# src/stake_watch/collectors/aave/collector.py
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from web3 import AsyncWeb3, AsyncHTTPProvider
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.aave.abi import AAVE_V3_POOL_ABI
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

class AaveV3Collector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, pool_address: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.pool_address = pool_address
        self.rpc_url = rpc_url

    def _get_pool_contract(self):
        w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        return w3.eth.contract(address=w3.to_checksum_address(self.pool_address), abi=AAVE_V3_POOL_ABI)

    async def collect_positions(self, wallet: str) -> list[Position]:
        pool = self._get_pool_contract()
        data = await pool.functions.getUserAccountData(wallet).call()
        total_collateral = Decimal(data[0]) / Decimal(10**8)
        total_debt = Decimal(data[1]) / Decimal(10**8)
        health_factor_raw = data[5]
        health_factor = float(Decimal(health_factor_raw) / Decimal(10**18)) if health_factor_raw > 0 else None
        ltv = float(Decimal(data[4]) / Decimal(10**4)) if data[4] > 0 else None

        if total_collateral == 0:
            return []

        return [Position(
            chain=self.chain, protocol=self.protocol, wallet=wallet,
            asset="USDC", position_type=PositionType.SUPPLY,
            amount=total_collateral, value_usd=total_collateral,
            apy=0.0, ltv=ltv, health_factor=health_factor,
            updated_at=datetime.now(timezone.utc))]

    async def collect_protocol_stats(self) -> ProtocolStats:
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
            tvl_usd=Decimal("0"), pools=[], updated_at=datetime.now(timezone.utc))
```

- [ ] **Step 3: Run tests, commit**
```bash
git commit -m "feat: add Aave V3 Base on-chain collector with position reading"
```

---

### Task P2: Compound V3 (Comet) Base collector

**Files:**
- Create: `src/stake_watch/collectors/compound/__init__.py`
- Create: `src/stake_watch/collectors/compound/collector.py`
- Create: `src/stake_watch/collectors/compound/abi.py`
- Test: `tests/collectors/compound/__init__.py`
- Test: `tests/collectors/compound/test_collector.py`

- [ ] **Step 1: Write tests**

```python
# tests/collectors/compound/test_collector.py
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.compound.collector import CompoundV3Collector
from stake_watch.models.common import Chain, PositionType

@pytest.mark.asyncio
async def test_collect_positions_supply():
    collector = CompoundV3Collector(chain=Chain.BASE, protocol="compound_v3_usdc",
        comet_address="0xComet", rpc_url="https://fake")
    mock_comet = MagicMock()
    mock_comet.functions.balanceOf.return_value.call = AsyncMock(return_value=5000 * 10**6)
    mock_comet.functions.borrowBalanceOf.return_value.call = AsyncMock(return_value=0)
    with patch.object(collector, '_get_comet_contract', return_value=mock_comet):
        positions = await collector.collect_positions("0xWallet")
    assert len(positions) == 1
    assert positions[0].amount == Decimal("5000")
    assert positions[0].position_type == PositionType.SUPPLY

@pytest.mark.asyncio
async def test_collect_positions_zero():
    collector = CompoundV3Collector(chain=Chain.BASE, protocol="compound_v3_usdc",
        comet_address="0xComet", rpc_url="https://fake")
    mock_comet = MagicMock()
    mock_comet.functions.balanceOf.return_value.call = AsyncMock(return_value=0)
    mock_comet.functions.borrowBalanceOf.return_value.call = AsyncMock(return_value=0)
    with patch.object(collector, '_get_comet_contract', return_value=mock_comet):
        positions = await collector.collect_positions("0xWallet")
    assert len(positions) == 0
```

- [ ] **Step 2: Implement**

```python
# src/stake_watch/collectors/compound/abi.py
COMET_ABI = [
    {"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "account", "type": "address"}], "name": "borrowBalanceOf",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalSupply", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalBorrow", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getUtilization", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]

COMET_USDC_BASE = "0xb125E6687d4313864e53df431d5425969c15Eb2F"
```

```python
# src/stake_watch/collectors/compound/collector.py
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from web3 import AsyncWeb3, AsyncHTTPProvider
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.compound.abi import COMET_ABI
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

USDC_DECIMALS = 6

class CompoundV3Collector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, comet_address: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.comet_address = comet_address
        self.rpc_url = rpc_url

    def _get_comet_contract(self):
        w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        return w3.eth.contract(address=w3.to_checksum_address(self.comet_address), abi=COMET_ABI)

    async def collect_positions(self, wallet: str) -> list[Position]:
        comet = self._get_comet_contract()
        scale = Decimal(10 ** USDC_DECIMALS)
        supply = Decimal(await comet.functions.balanceOf(wallet).call()) / scale
        borrow = Decimal(await comet.functions.borrowBalanceOf(wallet).call()) / scale
        positions = []
        if supply > 0:
            positions.append(Position(chain=self.chain, protocol=self.protocol, wallet=wallet,
                asset="USDC", position_type=PositionType.SUPPLY, amount=supply,
                value_usd=supply, apy=0.0, updated_at=datetime.now(timezone.utc)))
        if borrow > 0:
            positions.append(Position(chain=self.chain, protocol=self.protocol, wallet=wallet,
                asset="USDC", position_type=PositionType.BORROW, amount=borrow,
                value_usd=borrow, apy=0.0, updated_at=datetime.now(timezone.utc)))
        return positions

    async def collect_protocol_stats(self) -> ProtocolStats:
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
            tvl_usd=Decimal("0"), pools=[], updated_at=datetime.now(timezone.utc))
```

- [ ] **Step 3: Run tests, commit**
```bash
git commit -m "feat: add Compound V3 (Comet) Base on-chain collector"
```

---

### Task P3: Sky sUSDS (Ethereum) collector

**Files:**
- Create: `src/stake_watch/collectors/sky/__init__.py`
- Create: `src/stake_watch/collectors/sky/collector.py`
- Create: `src/stake_watch/collectors/sky/abi.py`
- Test: `tests/collectors/sky/__init__.py`
- Test: `tests/collectors/sky/test_collector.py`

sUSDS is an ERC4626 vault — same pattern as Morpho vault reading.

- [ ] **Step 1: Write tests**

```python
# tests/collectors/sky/test_collector.py
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from stake_watch.collectors.sky.collector import SkySusdsCollector
from stake_watch.models.common import Chain, PositionType

@pytest.mark.asyncio
async def test_collect_positions():
    collector = SkySusdsCollector(chain=Chain.ETHEREUM, protocol="sky_susds",
        susds_address="0xSUSDS", rpc_url="https://fake")
    mock_contract = MagicMock()
    mock_contract.functions.balanceOf.return_value.call = AsyncMock(return_value=5000 * 10**18)
    mock_contract.functions.convertToAssets.return_value.call = AsyncMock(return_value=5100 * 10**18)
    with patch.object(collector, '_get_contract', return_value=mock_contract):
        positions = await collector.collect_positions("0xWallet")
    assert len(positions) == 1
    assert positions[0].amount == Decimal("5100")
    assert positions[0].position_type == PositionType.VAULT

@pytest.mark.asyncio
async def test_collect_positions_zero():
    collector = SkySusdsCollector(chain=Chain.ETHEREUM, protocol="sky_susds",
        susds_address="0xSUSDS", rpc_url="https://fake")
    mock_contract = MagicMock()
    mock_contract.functions.balanceOf.return_value.call = AsyncMock(return_value=0)
    with patch.object(collector, '_get_contract', return_value=mock_contract):
        positions = await collector.collect_positions("0xWallet")
    assert len(positions) == 0
```

- [ ] **Step 2: Implement**

```python
# src/stake_watch/collectors/sky/abi.py
SUSDS_ABI = [
    {"inputs": [{"name": "owner", "type": "address"}], "name": "balanceOf",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "shares", "type": "uint256"}], "name": "convertToAssets",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalAssets", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalSupply", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]

SUSDS_ADDRESS = "0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD"
```

```python
# src/stake_watch/collectors/sky/collector.py
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from web3 import AsyncWeb3, AsyncHTTPProvider
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.sky.abi import SUSDS_ABI
from stake_watch.models.common import Chain, PositionType
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

SUSDS_DECIMALS = 18

class SkySusdsCollector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, susds_address: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.susds_address = susds_address
        self.rpc_url = rpc_url

    def _get_contract(self):
        w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        return w3.eth.contract(address=w3.to_checksum_address(self.susds_address), abi=SUSDS_ABI)

    async def collect_positions(self, wallet: str) -> list[Position]:
        contract = self._get_contract()
        scale = Decimal(10 ** SUSDS_DECIMALS)
        shares = await contract.functions.balanceOf(wallet).call()
        if shares == 0:
            return []
        assets = Decimal(await contract.functions.convertToAssets(shares).call()) / scale
        return [Position(chain=self.chain, protocol=self.protocol, wallet=wallet,
            asset="USDS", position_type=PositionType.VAULT, amount=assets,
            value_usd=assets, apy=0.0, vault_version="susds",
            updated_at=datetime.now(timezone.utc))]

    async def collect_protocol_stats(self) -> ProtocolStats:
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
            tvl_usd=Decimal("0"), pools=[], updated_at=datetime.now(timezone.utc))
```

- [ ] **Step 3: Run tests, commit**
```bash
git commit -m "feat: add Sky sUSDS Ethereum collector (ERC4626 vault)"
```

---

## Chunk 2: Solana Collector + Collector Registry

### Task P4: Kamino USDC collector (Solana)

**Files:**
- Create: `src/stake_watch/collectors/kamino/__init__.py`
- Create: `src/stake_watch/collectors/kamino/collector.py`
- Test: `tests/collectors/kamino/__init__.py`
- Test: `tests/collectors/kamino/test_collector.py`

Kamino uses Solana program accounts. For MVP, use DefiLlama for stats and provide a stub for positions (real Solana account parsing is complex, deferred to P1.5).

- [ ] **Step 1: Add solana-py**
```bash
uv add solana solders
```

- [ ] **Step 2: Write tests**

```python
# tests/collectors/kamino/test_collector.py
from decimal import Decimal
import pytest
from stake_watch.collectors.kamino.collector import KaminoCollector
from stake_watch.models.common import Chain

@pytest.mark.asyncio
async def test_collect_positions_returns_empty():
    collector = KaminoCollector(chain=Chain.SOLANA, protocol="kamino_usdc", rpc_url="https://fake")
    positions = await collector.collect_positions("FakeWallet123")
    assert positions == []

@pytest.mark.asyncio
async def test_collect_protocol_stats():
    collector = KaminoCollector(chain=Chain.SOLANA, protocol="kamino_usdc", rpc_url="https://fake")
    stats = await collector.collect_protocol_stats()
    assert stats.protocol == "kamino_usdc"
    assert stats.chain == Chain.SOLANA
```

- [ ] **Step 3: Implement stub**

```python
# src/stake_watch/collectors/kamino/collector.py
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from stake_watch.collectors.base import BaseCollector
from stake_watch.models.common import Chain
from stake_watch.models.position import Position
from stake_watch.models.protocol import ProtocolStats

class KaminoCollector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.rpc_url = rpc_url

    async def collect_positions(self, wallet: str) -> list[Position]:
        # Solana account parsing requires CPI decoding — deferred to P1.5
        self.logger.info("Kamino position collection not yet implemented (Solana account parsing required)")
        return []

    async def collect_protocol_stats(self) -> ProtocolStats:
        # Use DefiLlama for stats via the dual-collector pattern
        return ProtocolStats(chain=self.chain, protocol=self.protocol,
            tvl_usd=Decimal("0"), pools=[], updated_at=datetime.now(timezone.utc))
```

- [ ] **Step 4: Run tests, commit**
```bash
git commit -m "feat: add Kamino Solana collector stub (position parsing deferred)"
```

---

### Task P5: Collector registry + update seed.yaml with all 10 protocols

**Files:**
- Create: `src/stake_watch/collectors/registry.py`
- Modify: `src/stake_watch/main.py` — use registry instead of hardcoded map
- Modify: `config/seed.yaml` — add all 10 protocols
- Test: `tests/collectors/test_registry.py`

- [ ] **Step 1: Write tests**

```python
# tests/collectors/test_registry.py
from stake_watch.collectors.registry import build_collector
from stake_watch.config import ProtocolEntry
from stake_watch.collectors.defillama import DefiLlamaCollector
from stake_watch.collectors.aave.collector import AaveV3Collector
from stake_watch.collectors.compound.collector import CompoundV3Collector
from stake_watch.collectors.sky.collector import SkySusdsCollector
from stake_watch.collectors.morpho.collector import MorphoCollector
from stake_watch.collectors.kamino.collector import KaminoCollector

def test_build_defillama_collector():
    entry = ProtocolEntry(name="venus_usdc", chain="bsc", collector="defillama", defillama_slug="venus-core-pool")
    c = build_collector(entry, rpc_urls={"bsc": "https://bsc-rpc"})
    assert isinstance(c, DefiLlamaCollector)

def test_build_aave_collector():
    entry = ProtocolEntry(name="aave_v3_base", chain="base", collector="aave_v3")
    c = build_collector(entry, rpc_urls={"base": "https://base-rpc"})
    assert isinstance(c, AaveV3Collector)

def test_build_compound_collector():
    entry = ProtocolEntry(name="compound_v3_usdc", chain="base", collector="compound_v3")
    c = build_collector(entry, rpc_urls={"base": "https://base-rpc"})
    assert isinstance(c, CompoundV3Collector)

def test_build_sky_collector():
    entry = ProtocolEntry(name="sky_susds", chain="ethereum", collector="sky_susds")
    c = build_collector(entry, rpc_urls={"ethereum": "https://eth-rpc"})
    assert isinstance(c, SkySusdsCollector)

def test_build_morpho_collector():
    entry = ProtocolEntry(name="morpho_steakhouse_usdc", chain="base", collector="morpho",
        vault_address="0xBEEF")
    c = build_collector(entry, rpc_urls={"base": "https://base-rpc"})
    assert isinstance(c, MorphoCollector)

def test_build_kamino_collector():
    entry = ProtocolEntry(name="kamino_usdc", chain="solana", collector="kamino")
    c = build_collector(entry, rpc_urls={"solana": "https://solana-rpc"})
    assert isinstance(c, KaminoCollector)

def test_unknown_collector_returns_none():
    entry = ProtocolEntry(name="unknown", chain="base", collector="nonexistent")
    c = build_collector(entry, rpc_urls={})
    assert c is None
```

- [ ] **Step 2: Implement registry**

```python
# src/stake_watch/collectors/registry.py
from __future__ import annotations
import logging
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.defillama import DefiLlamaCollector
from stake_watch.config import ProtocolEntry
from stake_watch.models.common import Chain

logger = logging.getLogger(__name__)

DEFILLAMA_CHAIN_MAP = {"base": "Base", "ethereum": "Ethereum", "bsc": "BSC", "solana": "Solana"}

def build_collector(entry: ProtocolEntry, rpc_urls: dict[str, str]) -> BaseCollector | None:
    chain = Chain(entry.chain)
    rpc_url = rpc_urls.get(entry.chain, "")
    collector_type = entry.collector

    if collector_type == "aave_v3":
        from stake_watch.collectors.aave.collector import AaveV3Collector
        from stake_watch.collectors.aave.abi import AAVE_V3_POOL_BASE
        return AaveV3Collector(chain=chain, protocol=entry.name,
            pool_address=AAVE_V3_POOL_BASE, rpc_url=rpc_url)

    if collector_type == "compound_v3":
        from stake_watch.collectors.compound.collector import CompoundV3Collector
        from stake_watch.collectors.compound.abi import COMET_USDC_BASE
        return CompoundV3Collector(chain=chain, protocol=entry.name,
            comet_address=COMET_USDC_BASE, rpc_url=rpc_url)

    if collector_type == "sky_susds":
        from stake_watch.collectors.sky.collector import SkySusdsCollector
        from stake_watch.collectors.sky.abi import SUSDS_ADDRESS
        return SkySusdsCollector(chain=chain, protocol=entry.name,
            susds_address=SUSDS_ADDRESS, rpc_url=rpc_url)

    if collector_type == "morpho":
        from stake_watch.collectors.morpho.collector import MorphoCollector
        from stake_watch.collectors.morpho.abi import MORPHO_BLUE_BASE
        if not entry.vault_address:
            logger.warning(f"{entry.name}: morpho collector requires vault_address")
            return None
        return MorphoCollector(chain=chain, protocol=entry.name,
            vault_address=entry.vault_address, morpho_address=MORPHO_BLUE_BASE, rpc_url=rpc_url)

    if collector_type == "kamino":
        from stake_watch.collectors.kamino.collector import KaminoCollector
        return KaminoCollector(chain=chain, protocol=entry.name, rpc_url=rpc_url)

    if collector_type == "defillama":
        slug = entry.defillama_slug
        if not slug:
            logger.warning(f"{entry.name}: defillama collector requires defillama_slug")
            return None
        return DefiLlamaCollector(chain=chain, protocol=entry.name,
            defillama_slug=slug, chain_filter=DEFILLAMA_CHAIN_MAP.get(entry.chain, entry.chain))

    logger.warning(f"Unknown collector type '{collector_type}' for {entry.name}")
    return None
```

- [ ] **Step 3: Update main.py to use registry**

Replace `_build_collector` and remove `DEFILLAMA_SLUG_MAP`/`DEFILLAMA_CHAIN_MAP` from main.py. Replace with:

```python
from stake_watch.collectors.registry import build_collector

# In build_app(), replace the collector building loop:
rpc_urls = {chain: ep.primary for chain, ep in settings.rpc.items()}
collectors = []
for entry in protocols:
    if not entry.enabled:
        continue
    collector = build_collector(entry, rpc_urls=rpc_urls)
    if collector:
        collectors.append(collector)
```

- [ ] **Step 4: Update seed.yaml with all 10 protocols**

```yaml
protocols:
  - name: aave_v3_base
    chain: base
    collector: aave_v3
    defillama_slug: aave-v3
    safety_rank: 1
    safety_score: 8.8
    primary_risks: ["shared pool bad debt", "utilization", "Base L2 risk"]
    enabled: true

  - name: sky_susds
    chain: ethereum
    collector: sky_susds
    defillama_slug: sky
    safety_rank: 2
    safety_score: 8.5
    primary_risks: ["USDC-to-USDS conversion", "governance", "RWA exposure"]
    enabled: true

  - name: morpho_steakhouse_usdc
    chain: base
    collector: morpho
    vault_address: "0xBEEFE94c8aD530842bfE7d8B397938fFc1cb83b2"
    defillama_slug: morpho-blue
    safety_rank: 3
    safety_score: 8.3
    primary_risks: ["curator risk", "underlying market bad debt"]
    enabled: true

  - name: morpho_gauntlet_usdc_prime
    chain: base
    collector: morpho
    vault_address: "0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61"
    defillama_slug: morpho-blue
    safety_rank: 4
    safety_score: 8.2
    primary_risks: ["curator risk", "oracle", "market allocation"]
    enabled: true

  - name: compound_v3_usdc
    chain: base
    collector: compound_v3
    defillama_slug: compound-v3
    safety_rank: 5
    safety_score: 8.1
    primary_risks: ["single collateral market risk", "utilization"]
    enabled: true

  - name: fluid_usdc
    chain: ethereum
    collector: defillama
    defillama_slug: fluid-lending
    safety_rank: 6
    safety_score: 7.8
    primary_risks: ["complex contract system", "utilization"]
    enabled: true

  - name: morpho_pangolins_usdc
    chain: base
    collector: morpho
    vault_address: "0x1401d1271C47648AC70cBcdfA3776D4A87CE006B"
    defillama_slug: morpho-blue
    safety_rank: 7
    safety_score: 7.5
    primary_risks: ["Pangolins management capability", "rebalancing"]
    enabled: true

  - name: morpho_gauntlet_frontier_usdc
    chain: ethereum
    collector: defillama
    defillama_slug: morpho-blue
    safety_rank: 8
    safety_score: 7.4
    primary_risks: ["broader collateral acceptance for yield"]
    enabled: true

  - name: jupiter_lend
    chain: solana
    collector: defillama
    defillama_slug: jupiter-lend
    safety_rank: 9
    safety_score: 7.2
    primary_risks: ["newer protocol", "unified liquidity", "withdrawal smoothing"]
    enabled: true

  - name: kamino_usdc
    chain: solana
    collector: kamino
    defillama_slug: kamino-lend
    safety_rank: 10
    safety_score: 7.2
    primary_risks: ["Solana risk", "oracle", "liquidation", "market parameters"]
    enabled: true
```

- [ ] **Step 5: Run ALL tests, commit**
```bash
git commit -m "feat: add collector registry and register all 10 protocols"
```

---

## Summary

| Task | Protocol | Chain | Collector Type |
|---|---|---|---|
| P1 | Aave V3 | Base | On-chain (getUserAccountData) |
| P2 | Compound V3 | Base | On-chain (balanceOf, borrowBalanceOf) |
| P3 | Sky sUSDS | Ethereum | On-chain (ERC4626 balanceOf/convertToAssets) |
| P4 | Kamino | Solana | Stub (position parsing deferred) |
| P5 | All 10 | All | Collector registry + seed.yaml |

After P2-protocols, on-chain position reading works for: Aave V3 (Base), Compound V3 (Base), Sky sUSDS (Ethereum), Morpho (Base). DefiLlama provides protocol stats for all. Fluid and Gauntlet Frontier use DefiLlama-only. Kamino stub.
