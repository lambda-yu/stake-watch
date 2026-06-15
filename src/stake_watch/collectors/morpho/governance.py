from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel
from web3 import AsyncWeb3


# Precomputed keccak256 hashes of MetaMorpho vault governance event signatures.
# Computed offline so we don't depend on web3 at import time.
EVENT_TOPICS: dict[str, str] = {
    "SetCurator": "0xbd0a63c12948fbc9194a5839019f99c9d71db924e5c70018265bc778b8f1a506",
    "SetGuardian": "0x31845eceb9cde510c7e8b37f76301c688feb70bc9653aa4c28a3734999840fd8",
    "SetIsAllocator": "0x74dc60cbc81a9472d04ad1d20e151d369c41104d655ed3f2f3091166a502cd8d",
    "SetFee": "0x01fe2943baee27f47add82886c2200f910c749c461c9b63c5fe83901a53bdb49",
    "SubmitCap": "0xe851bb5856808a50efd748be463b8f35bcfb5ec74c5bfde776fe0a4d2a26db27",
    "AcceptCap": "0xaa1c6af41a8bc51bdf39fa36aff278bc572255d57e1b51c1785ddb0d02577e09",
    "SetSupplyQueue": "0x6ce31538fc7fba95714ddc8a275a09252b4b1fb8f33d2550aa58a5f62ad934de",
    "UpdateWithdrawQueue": "0x01580e441f843ce381a03ed861dea41a7b499adc41d479846b0728e9202e297b",
    "SubmitTimelock": "0xb3aa0ade2442acf51d06713c2d1a5a3ec0373cce969d42b53f4689f97bccf380",
    "SetTimelock": "0xd28e9b90ee9b37c5936ff84392d71f29ff18117d7e76bcee60615262a90a3f75",
}


class GovernanceEvent(BaseModel):
    vault_address: str
    event_type: str
    block_number: int
    tx_hash: str
    raw_data: str
    detected_at: datetime


class GovernanceMonitor:
    def __init__(self, vault_address: str, rpc_url: str):
        self.vault_address = vault_address
        self.rpc_url = rpc_url
        self._last_block: int = 0

    async def check_recent_events(
        self, lookback_blocks: int = 1000
    ) -> list[GovernanceEvent]:
        """Poll for governance events in recent blocks."""
        w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.rpc_url))
        try:
            latest = await w3.eth.block_number
        except Exception:
            return []

        from_block = max(latest - lookback_blocks, self._last_block + 1, 0)
        if from_block > latest:
            return []

        topics = list(EVENT_TOPICS.values())

        try:
            logs = await w3.eth.get_logs(
                {
                    "address": w3.to_checksum_address(self.vault_address),
                    "fromBlock": from_block,
                    "toBlock": latest,
                    "topics": [topics],
                }
            )
        except Exception:
            return []

        events: list[GovernanceEvent] = []
        for log in logs:
            topic0 = log.get("topics", [b""])[0]
            topic_hex = (
                "0x" + topic0.hex() if isinstance(topic0, bytes) else topic0
            )
            event_name = next(
                (name for name, t in EVENT_TOPICS.items() if t == topic_hex),
                "Unknown",
            )
            tx_hash_raw = log.get("transactionHash", b"")
            tx_hash = (
                "0x" + tx_hash_raw.hex()
                if isinstance(tx_hash_raw, bytes)
                else str(tx_hash_raw)
            )
            data_raw = log.get("data", b"")
            raw_data = (
                "0x" + data_raw.hex()
                if isinstance(data_raw, bytes)
                else str(data_raw)
            )
            events.append(
                GovernanceEvent(
                    vault_address=self.vault_address,
                    event_type=event_name,
                    block_number=log.get("blockNumber", 0),
                    tx_hash=tx_hash,
                    raw_data=raw_data,
                    detected_at=datetime.now(timezone.utc),
                )
            )

        self._last_block = latest
        return events
