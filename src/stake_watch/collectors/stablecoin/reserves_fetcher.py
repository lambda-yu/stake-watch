from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

TETHER_URL = "https://app.tether.to/transparency.json"
CIRCLE_SUPPLY_URL = "https://api.circle.com/v1/stablecoins"

TETHER_CHAIN_MAP = {
    "eth": "Ethereum", "trx": "Tron", "sol": "Solana", "ava": "Avalanche",
    "bnb": "BSC", "algo": "Algorand", "eos": "EOS", "near": "Near",
    "ton": "TON", "celo": "Celo", "aptos": "Aptos", "kaia": "Kaia",
    "omni": "Omni", "liquid": "Liquid",
}


async def fetch_tether_reserves() -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            resp = await client.get(TETHER_URL)
            resp.raise_for_status()
            raw = resp.json()

        data = raw.get("data", raw)
        usdt = data.get("usdt", data) if isinstance(data, dict) else data

        total_assets = Decimal(str(usdt.get("total_assets", 0) or 0))
        total_liabilities = Decimal(str(usdt.get("total_liabilities", 0) or 0))
        equity = Decimal(str(usdt.get("shareholders_equity", 0) or 0))

        chains = {}
        for suffix, name in TETHER_CHAIN_MAP.items():
            authorized = Decimal(str(usdt.get(f"totaltokens_{suffix}", 0) or 0))
            reserve = Decimal(str(usdt.get(f"reserve_balance_{suffix}", 0) or 0))
            issued = authorized - reserve
            if issued > 1000:
                chains[name] = float(issued)

        return {
            "token": "USDT",
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "equity": equity,
            "coverage_ratio": float(total_assets / total_liabilities) if total_liabilities > 0 else 0,
            "chains": chains,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to fetch Tether data: {e}")
        return None


async def fetch_circle_supply() -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(CIRCLE_SUPPLY_URL)
            resp.raise_for_status()
            raw = resp.json()

        stablecoins = raw.get("data", raw)
        if not isinstance(stablecoins, list):
            stablecoins = [stablecoins]

        usdc = None
        for s in stablecoins:
            if s.get("symbol") == "USDC":
                usdc = s
                break

        if not usdc:
            return None

        total = Decimal(str(usdc.get("totalAmount", 0)))
        chains = {}
        for c in usdc.get("chains", []):
            name = c.get("chain", "unknown")
            amount = Decimal(str(c.get("amount", 0)))
            if amount > 0:
                chains[name] = float(amount)

        return {
            "token": "USDC",
            "total_supply": total,
            "chains": chains,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to fetch Circle data: {e}")
        return None
