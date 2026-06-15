from __future__ import annotations
from pydantic import BaseModel

STABLECOIN_WHITELIST = {
    "USDC": {
        "ethereum": [{"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "type": "native", "risk_premium": 0}],
        "base": [
            {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "type": "native", "risk_premium": 0},
            {"address": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "type": "bridged", "risk_premium": 10},
        ],
        "solana": [{"address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "type": "native", "risk_premium": 0}],
        "bsc": [{"address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "type": "native", "risk_premium": 0}],
    },
    "USDT": {
        "ethereum": [{"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "type": "native", "risk_premium": 0}],
        "tron": [{"address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "type": "native", "risk_premium": 0}],
        "bsc": [{"address": "0x55d398326f99059fF775485246999027B3197955", "type": "native", "risk_premium": 0}],
        "solana": [{"address": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "type": "native", "risk_premium": 0}],
    },
    "USD0": {
        "ethereum": [{"address": "0x73a15fed60bf67631dc6cd7bc5b6e8da8190acf5", "type": "native", "risk_premium": 0}],
    },
    "USD1": {
        "ethereum": [{"address": "0x8d0d000ee44948fc98c9b98a4fa4921476f08b0d", "type": "native", "risk_premium": 0}],
    },
}

class VerificationResult(BaseModel):
    address: str
    token: str
    chain: str
    is_verified: bool
    token_type: str  # "native" | "bridged" | "unknown"
    risk_premium: int

class CrossChainVerifier:
    def verify(self, address: str, token: str, chain: str) -> VerificationResult:
        entries = STABLECOIN_WHITELIST.get(token, {}).get(chain, [])
        for entry in entries:
            if entry["address"].lower() == address.lower():
                return VerificationResult(address=address, token=token, chain=chain,
                    is_verified=True, token_type=entry["type"], risk_premium=entry["risk_premium"])
        return VerificationResult(address=address, token=token, chain=chain,
            is_verified=False, token_type="unknown", risk_premium=100)
