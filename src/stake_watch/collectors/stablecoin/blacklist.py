from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel
from web3 import AsyncWeb3, AsyncHTTPProvider

USDC_ADDRESSES = {
    "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
}
USDT_ADDRESSES = {
    "ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
}

BLACKLIST_ABI_USDC = [{"inputs": [{"name": "_account", "type": "address"}], "name": "isBlacklisted",
    "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"}]
BLACKLIST_ABI_USDT = [{"inputs": [{"name": "_maker", "type": "address"}], "name": "isBlackListed",
    "outputs": [{"type": "bool"}], "stateMutability": "view", "type": "function"}]

class BlacklistResult(BaseModel):
    wallet: str
    token: str
    chain: str
    is_blacklisted: bool
    checked_at: datetime

class BlacklistChecker:
    def _get_contract(self, token: str, chain: str, rpc_url: str):
        w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        if token == "USDC":
            addr = USDC_ADDRESSES.get(chain, "")
            return w3.eth.contract(address=w3.to_checksum_address(addr), abi=BLACKLIST_ABI_USDC)
        else:
            addr = USDT_ADDRESSES.get(chain, "")
            return w3.eth.contract(address=w3.to_checksum_address(addr), abi=BLACKLIST_ABI_USDT)

    async def check(self, wallet: str, token: str, chain: str, rpc_url: str) -> BlacklistResult:
        contract = self._get_contract(token, chain, rpc_url)
        try:
            if token == "USDC":
                result = await contract.functions.isBlacklisted(wallet).call()
            else:
                result = await contract.functions.isBlackListed(wallet).call()
        except Exception:
            result = False
        return BlacklistResult(wallet=wallet, token=token, chain=chain,
            is_blacklisted=result, checked_at=datetime.now(timezone.utc))
