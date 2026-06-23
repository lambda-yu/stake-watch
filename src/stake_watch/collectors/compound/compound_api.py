"""Compound V3 official REST API client.

Endpoint: https://v3-api.compound.finance/market/{chain}/{cometAddress}/summary
"""
from __future__ import annotations

import asyncio
import httpx

# Known USDC/USDT comets for Compound V3
# Each entry: (chain_path, comet_address, chain_short, chain_full, base_asset)
COMETS = [
    ("mainnet",      "0xc3d688B66703497DAA19211EEdff47f25384cdc3", "ETH",  "Ethereum", "USDC"),
    ("mainnet",      "0x3Afdc9BCA9213A35503b077a6072F3D0d5AB0840", "ETH",  "Ethereum", "USDT"),
    ("base-mainnet", "0xb125E6687d4313864e53df431d5425969c15Eb2F", "BASE", "Base",     "USDC"),
]


async def _fetch_one(client: httpx.AsyncClient, chain_path: str, comet: str):
    url = f"https://v3-api.compound.finance/market/{chain_path}/{comet}/summary"
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def fetch_compound_v3_stable_data() -> list[dict]:
    """Return per-chain USDC/USDT aggregate APY/TVL across Compound V3 comets.

    Each entry: {chain, chain_full, by_asset: {USDC/USDT: {apy, tvl_usd, pools}}, tvl_usd, apy, pools}
    """
    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(*[
            _fetch_one(client, cp, addr) for cp, addr, _, _, _ in COMETS
        ])

    by_chain: dict[str, dict] = {}
    for (chain_path, comet, short, full, asset), data in zip(COMETS, results):
        if not data:
            continue
        try:
            apy = float(data.get("supply_apr", 0)) * 100
            borrow_apy = float(data.get("borrow_apr", 0)) * 100
            base_price = float(data.get("base_usd_price", 1))
            supply_amount = float(data.get("total_supply_value", 0))
            borrow_amount = float(data.get("total_borrow_value", 0))
            collateral_value = float(data.get("total_collateral_value", 0))
            tvl_usd = supply_amount * base_price
            avail_liq_usd = max(0, supply_amount - borrow_amount) * base_price
            withdrawable_ratio = (avail_liq_usd / tvl_usd) if tvl_usd > 0 else 0
            util_raw = data.get("utilization", "0")
            util = float(util_raw) / 1e18 if util_raw else 0
            borrow_usd = borrow_amount * base_price
            coverage_ratio = (collateral_value / borrow_usd) if borrow_usd > 0 else 0
            bad_debt_ratio = max(0.0, 1 - coverage_ratio) if coverage_ratio > 0 else 0
        except (TypeError, ValueError):
            continue
        entry = by_chain.setdefault(short, {
            "chain": short, "chain_full": full,
            "tvl_usd": 0.0, "apy": 0.0, "pools": 0, "by_asset": {},
        })
        entry["by_asset"][asset] = {
            "apy": apy, "tvl_usd": tvl_usd, "pools": 1,
            "utilization": util,
            "borrow_apy": borrow_apy,
            "available_liquidity_usd": avail_liq_usd,
            "withdrawable_ratio": withdrawable_ratio,
            "collateral_coverage": coverage_ratio,
            "bad_debt_ratio": bad_debt_ratio,
        }
        entry["tvl_usd"] += tvl_usd
        entry["pools"] += 1

    result = []
    for entry in by_chain.values():
        usdc = entry["by_asset"].get("USDC")
        usdt = entry["by_asset"].get("USDT")
        if usdc and usdt:
            entry["apy"] = (usdc["apy"] + usdt["apy"]) / 2
        elif usdc:
            entry["apy"] = usdc["apy"]
        elif usdt:
            entry["apy"] = usdt["apy"]
        result.append(entry)
    result.sort(key=lambda x: -x["tvl_usd"])
    return result
