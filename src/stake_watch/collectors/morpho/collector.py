from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from web3 import AsyncWeb3, AsyncHTTPProvider
from stake_watch.collectors.base import BaseCollector
from stake_watch.collectors.morpho.abi import MORPHO_BLUE_ABI, METAMORPHO_VAULT_ABI
from stake_watch.collectors.morpho.vault import read_vault_state
from stake_watch.collectors.morpho.market import read_market_allocations
from stake_watch.models.common import Chain
from stake_watch.models.position import Position
from stake_watch.models.protocol import PoolStats, ProtocolStats

class MorphoCollector(BaseCollector):
    def __init__(self, chain: Chain, protocol: str, vault_address: str,
                 morpho_address: str, rpc_url: str):
        super().__init__(chain=chain, protocol=protocol)
        self.vault_address = vault_address
        self.morpho_address = morpho_address
        self.rpc_url = rpc_url

    def _get_contracts(self):
        w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        vault = w3.eth.contract(
            address=w3.to_checksum_address(self.vault_address),
            abi=METAMORPHO_VAULT_ABI)
        morpho = w3.eth.contract(
            address=w3.to_checksum_address(self.morpho_address),
            abi=MORPHO_BLUE_ABI)
        return vault, morpho

    async def collect_positions(self, wallet: str) -> list[Position]:
        return []

    async def collect_protocol_stats(self) -> ProtocolStats:
        vault_contract, morpho_contract = self._get_contracts()
        vault_state = await read_vault_state(vault_contract, self.vault_address)
        allocations = await read_market_allocations(
            vault_contract, morpho_contract, self.vault_address,
            total_vault_assets=vault_state.total_assets)
        pools = []
        for a in allocations:
            pools.append(PoolStats(
                pool_id=a.market_id[:18],
                asset=f"{a.collateral_token[:10]}/{a.loan_token[:10]}",
                supply_apy=0.0,
                borrow_apy=0.0,
                total_supply=a.supply_assets,
                total_borrow=a.borrow_assets,
                utilization=a.utilization))
        return ProtocolStats(
            chain=self.chain, protocol=self.protocol,
            tvl_usd=vault_state.total_assets,
            pools=pools, updated_at=datetime.now(timezone.utc))
