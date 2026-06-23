"""Aave V3 official GraphQL API client.

Endpoint: https://api.v3.aave.com/graphql
"""
from __future__ import annotations

import httpx

GRAPHQL_URL = "https://api.v3.aave.com/graphql"

# chainId -> our chain display name
CHAIN_ID_MAP = {
    1: ("ETH", "Ethereum"),
    8453: ("BASE", "Base"),
}

QUERY = """
{
  markets(request: { chainIds: [1, 8453] }) {
    name
    chain { chainId name }
    reserves {
      underlyingToken { symbol }
      size { usd }
      supplyInfo {
        apy { value }
        supplyCap { amount { value } usd }
        total { value }
        supplyCapReached
      }
      borrowInfo {
        apy { value }
        utilizationRate { value }
        availableLiquidity { amount { value } usd }
        borrowCap { amount { value } usd }
        total { amount { value } usd }
        borrowCapReached
      }
    }
  }
}
"""


async def fetch_aave_v3_stable_data() -> list[dict]:
    """Return per-chain USDC/USDT aggregate APY/TVL across Aave V3 markets.

    Each entry: {chain, chain_full, by_asset: {USDC: {apy, tvl_usd, pools}, USDT: ...}}
    Only includes Ethereum + Base main markets (excludes Lido/EtherFi sub-markets).
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(GRAPHQL_URL, json={"query": QUERY})
        resp.raise_for_status()
        data = resp.json()

    markets = (data.get("data") or {}).get("markets") or []

    # Only keep main markets per chain (e.g., AaveV3Ethereum, AaveV3Base) — skip sub-markets
    main_markets = [m for m in markets if m.get("name", "").startswith("AaveV3")
                    and not any(x in m["name"] for x in ("Lido", "EtherFi", "Horizon", "Sepolia"))]

    by_chain: dict[int, dict] = {}
    for m in main_markets:
        chain_id = m["chain"]["chainId"]
        if chain_id not in CHAIN_ID_MAP:
            continue
        short, full = CHAIN_ID_MAP[chain_id]
        entry = by_chain.setdefault(chain_id, {
            "chain": short, "chain_full": full,
            "tvl_usd": 0.0, "apy": 0.0, "pools": 0, "by_asset": {},
        })
        for r in m.get("reserves", []):
            symbol = (r.get("underlyingToken") or {}).get("symbol", "").upper()
            if symbol not in ("USDC", "USDT"):
                continue
            try:
                sup = r.get("supplyInfo") or {}
                bor = r.get("borrowInfo") or {}
                apy = float((sup.get("apy") or {}).get("value", 0)) * 100
                borrow_apy = float((bor.get("apy") or {}).get("value", 0)) * 100
                tvl = float((r.get("size") or {}).get("usd", 0))
                util = float((bor.get("utilizationRate") or {}).get("value", 0))
                supply_total = float((sup.get("total") or {}).get("value", 0))
                borrow_total = float(((bor.get("total") or {}).get("amount") or {}).get("value", 0))
                supply_cap_amt = float(((sup.get("supplyCap") or {}).get("amount") or {}).get("value", 0))
                borrow_cap_amt = float(((bor.get("borrowCap") or {}).get("amount") or {}).get("value", 0))
                avail_liq_usd = float((bor.get("availableLiquidity") or {}).get("usd", 0))
                supply_cap_usage = (supply_total / supply_cap_amt) if supply_cap_amt > 0 else 0
                borrow_cap_usage = (borrow_total / borrow_cap_amt) if borrow_cap_amt > 0 else 0
                withdrawable_ratio = (avail_liq_usd / tvl) if tvl > 0 else 0
            except (TypeError, ValueError):
                continue
            entry["by_asset"][symbol] = {
                "apy": apy, "tvl_usd": tvl, "pools": 1,
                "utilization": util,
                "borrow_apy": borrow_apy,
                "supply_cap_usage": supply_cap_usage,
                "borrow_cap_usage": borrow_cap_usage,
                "available_liquidity_usd": avail_liq_usd,
                "withdrawable_ratio": withdrawable_ratio,
            }
            entry["tvl_usd"] += tvl
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
        if entry["by_asset"]:
            result.append(entry)
    result.sort(key=lambda x: -x["tvl_usd"])
    return result
