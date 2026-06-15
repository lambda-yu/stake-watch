from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

TETHER_URL = "https://app.tether.to/transparency.json"
CIRCLE_SUPPLY_URL = "https://api.circle.com/v1/stablecoins"


async def fetch_tether_reserves() -> dict | None:
    """Fetch Tether transparency data: total assets, liabilities, equity."""
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            resp = await client.get(TETHER_URL)
            resp.raise_for_status()
            data = resp.json()

        usdt_data = None
        for entry in data if isinstance(data, list) else [data]:
            if entry.get("iso") == "usdt" or entry.get("symbol") == "$":
                usdt_data = entry
                break

        if not usdt_data:
            usdt_data = data[0] if isinstance(data, list) else data

        total_assets = Decimal(str(usdt_data.get("total_assets", 0)))
        total_liabilities = Decimal(str(usdt_data.get("total_liabilities", 0)))
        equity = Decimal(str(usdt_data.get("shareholders_equity", 0)))

        chains = {}
        for chain_data in usdt_data.get("tokens", []):
            name = chain_data.get("name", "unknown")
            authorized = Decimal(str(chain_data.get("total_authorized", 0)))
            reserve = Decimal(str(chain_data.get("reserve_balance", 0)))
            issued = authorized - reserve
            if issued > 0:
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
    """Fetch Circle USDC supply data per chain."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(CIRCLE_SUPPLY_URL)
            resp.raise_for_status()
            data = resp.json()

        stablecoins = data if isinstance(data, list) else [data]
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
