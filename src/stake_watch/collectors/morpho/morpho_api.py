"""Morpho GraphQL API client for fetching vault-specific APY and TVL.

Uses vault address as unique identifier (much more accurate than DefiLlama
which has duplicate symbols across multiple vaults).
"""
from __future__ import annotations

import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

MORPHO_API_URL = "https://blue-api.morpho.org/graphql"

CHAIN_IDS = {"base": 8453, "ethereum": 1}


async def fetch_vault_data(vault_address: str, chain: str = "base") -> dict | None:
    """Fetch live data for a specific Morpho vault by address.

    Returns: {tvl_usd, net_apy, apy, name, asset, symbol, share_price_usd,
              withdrawable_usd, withdrawable_ratio, utilization} or None.

    Liquidity model: a Morpho vault holds an idle cash tranche + supplies to
    N markets. The withdrawable amount equals
      idle_usd + Σ min(supplyAssetsUsd_per_market, market_liquidityAssetsUsd)
    `utilization` is exposed as a 1 - withdrawable_ratio proxy because vault
    contracts don't have a direct utilization concept.
    """
    chain_id = CHAIN_IDS.get(chain.lower(), 8453)
    query = """
    {
      vaults(where: { address_in: ["%s"], chainId_in: [%d] }) {
        items {
          name
          address
          symbol
          asset { symbol }
          state {
            totalAssetsUsd netApy apy sharePriceUsd
            allocation {
              supplyAssetsUsd
              market { state { liquidityAssetsUsd } }
            }
          }
        }
      }
    }
    """ % (vault_address, chain_id)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(MORPHO_API_URL, json={"query": query})
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data", {}).get("vaults", {}).get("items", [])
        if not items:
            return None
        v = items[0]
        st = v.get("state") or {}
        total_assets = float(st.get("totalAssetsUsd") or 0)

        allocations = st.get("allocation") or []
        supplied = 0.0
        withdrawable_from_markets = 0.0
        for a in allocations:
            supply_usd = float(a.get("supplyAssetsUsd") or 0)
            supplied += supply_usd
            market_liq = float(((a.get("market") or {}).get("state") or {})
                                .get("liquidityAssetsUsd") or 0)
            withdrawable_from_markets += min(supply_usd, market_liq)
        idle_usd = max(0.0, total_assets - supplied)
        withdrawable_usd = idle_usd + withdrawable_from_markets
        withdrawable_ratio = (withdrawable_usd / total_assets) if total_assets > 0 else 0.0
        utilization = max(0.0, 1.0 - withdrawable_ratio) if total_assets > 0 else 0.0

        return {
            "name": v.get("name"),
            "asset": v.get("asset", {}).get("symbol", "USDC"),
            "symbol": v.get("symbol"),
            "tvl_usd": total_assets,
            "apy": float(st.get("apy") or 0) * 100,
            "net_apy": float(st.get("netApy") or 0) * 100,
            "share_price_usd": float(st.get("sharePriceUsd") or 0),
            "withdrawable_usd": withdrawable_usd,
            "available_liquidity_usd": withdrawable_usd,
            "withdrawable_ratio": withdrawable_ratio,
            "utilization": utilization,
        }
    except Exception as e:
        logger.error(f"Morpho API error for {vault_address}: {e}")
        return None


HIGH_RISK_EVENT_TYPES = {
    "submitOwner", "acceptOwner",
    "submitCurator", "acceptCurator",
    "submitGuardian", "acceptGuardian",
    "submitTimelock", "acceptTimelock",
}


async def fetch_vault_admin_events(vault_address: str, chain: str = "base",
                                    limit: int = 50) -> list[dict] | None:
    """Fetch the latest admin events for a Morpho vault.

    Returns a list sorted newest-first: [{type, timestamp, hash, days_ago}, ...].
    """
    chain_id = CHAIN_IDS.get(chain.lower(), 8453)
    query = """
    {
      vaults(where: { address_in: ["%s"], chainId_in: [%d] }) {
        items {
          adminEvents { items { type timestamp hash } }
        }
      }
    }
    """ % (vault_address, chain_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(MORPHO_API_URL, json={"query": query})
            resp.raise_for_status()
            data = resp.json()
        items = (data.get("data") or {}).get("vaults", {}).get("items", [])
        if not items:
            return None
        events = items[0].get("adminEvents", {}).get("items", []) or []
    except Exception as e:
        logger.error(f"Morpho admin events error for {vault_address}: {e}")
        return None
    import time
    now = int(time.time())
    out = []
    for e in events:
        try:
            ts = int(e.get("timestamp") or 0)
        except (TypeError, ValueError):
            continue
        out.append({
            "type": e.get("type"),
            "timestamp": ts,
            "hash": e.get("hash"),
            "days_ago": (now - ts) / 86400,
        })
    out.sort(key=lambda x: -x["timestamp"])
    return out[:limit]


def summarize_vault_activity(events: list[dict]) -> dict:
    """Compress raw events into a risk-relevant summary."""
    if not events:
        return {"days_since_last_action": None, "last_action_type": None,
                "high_risk_recent": [], "reallocate_24h": 0}
    last = events[0]
    high_risk = [e for e in events if e["type"] in HIGH_RISK_EVENT_TYPES and e["days_ago"] < 7]
    realloc_24h = sum(1 for e in events
                      if e["type"] and "reallocate" in e["type"] and e["days_ago"] < 1)
    return {
        "days_since_last_action": last["days_ago"],
        "last_action_type": last["type"],
        "high_risk_recent": [{"type": e["type"], "days_ago": e["days_ago"]}
                              for e in high_risk],
        "reallocate_24h": realloc_24h,
    }


async def fetch_vault_bad_debt(vault_address: str, chain: str = "base") -> dict | None:
    """Aggregate per-market bad debt across a Morpho vault's allocations.

    Returns {bad_debt_usd, realized_bad_debt_usd, supply_usd, bad_debt_ratio}.
    """
    chain_id = CHAIN_IDS.get(chain.lower(), 8453)
    query = """
    {
      vaults(where: { address_in: ["%s"], chainId_in: [%d] }) {
        items {
          state {
            totalAssetsUsd
            allocation {
              supplyAssetsUsd
              market {
                badDebt { usd }
                realizedBadDebt { usd }
              }
            }
          }
        }
      }
    }
    """ % (vault_address, chain_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(MORPHO_API_URL, json={"query": query})
            resp.raise_for_status()
            data = resp.json()
        items = (data.get("data") or {}).get("vaults", {}).get("items", [])
        if not items:
            return None
        st = items[0].get("state") or {}
        total_assets = float(st.get("totalAssetsUsd") or 0)
        total_bad = 0.0
        total_realized = 0.0
        total_supply = 0.0
        for a in st.get("allocation", []) or []:
            m = a.get("market") or {}
            total_bad += float((m.get("badDebt") or {}).get("usd") or 0)
            total_realized += float((m.get("realizedBadDebt") or {}).get("usd") or 0)
            total_supply += float(a.get("supplyAssetsUsd") or 0)
    except Exception as e:
        logger.error(f"Morpho bad debt fetch failed for {vault_address}: {e}")
        return None
    denom = total_supply if total_supply > 0 else total_assets
    ratio = (total_bad / denom) if denom > 0 else 0
    return {
        "bad_debt_usd": total_bad,
        "realized_bad_debt_usd": total_realized,
        "supply_usd": total_supply,
        "vault_tvl_usd": total_assets,
        "bad_debt_ratio": ratio,
    }


async def fetch_vault_top_holders(vault_address: str, chain: str = "base",
                                    n: int = 10) -> dict | None:
    """Top N depositors of a Morpho vault + concentration ratios.

    Returns {top1_share, top5_share, top10_share, total_holders, holders}.
    Shares are ratios of TVL held by the top N addresses.
    """
    chain_id = CHAIN_IDS.get(chain.lower(), 8453)
    query = """
    {
      vaultPositions(first: %d, orderBy: Shares, orderDirection: Desc,
        where: { vaultAddress_in: ["%s"], chainId_in: [%d], shares_gte: "1" }) {
        items { user { address } state { assetsUsd } }
        pageInfo { countTotal }
      }
    }
    """ % (n, vault_address.lower(), chain_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(MORPHO_API_URL, json={"query": query})
            resp.raise_for_status()
            data = resp.json()
        res = (data.get("data") or {}).get("vaultPositions") or {}
        items = res.get("items") or []
        total_holders = (res.get("pageInfo") or {}).get("countTotal") or len(items)
    except Exception as e:
        logger.error(f"Morpho top-holders fetch failed for {vault_address}: {e}")
        return None
    holders = []
    for it in items:
        addr = (it.get("user") or {}).get("address") or ""
        usd = float((it.get("state") or {}).get("assetsUsd") or 0)
        holders.append({"address": addr, "assets_usd": usd})
    # Need vault tvl for ratios — fetch from existing api
    vault = await fetch_vault_data(vault_address, chain)
    tvl = float(vault["tvl_usd"]) if vault else 0
    if tvl <= 0:
        return None
    top1 = holders[0]["assets_usd"] if holders else 0
    top5 = sum(h["assets_usd"] for h in holders[:5])
    top10 = sum(h["assets_usd"] for h in holders[:10])
    return {
        "top1_share": top1 / tvl,
        "top5_share": top5 / tvl,
        "top10_share": top10 / tvl,
        "top1_address": holders[0]["address"] if holders else None,
        "total_holders": total_holders,
        "holders": holders,
        "vault_tvl_usd": tvl,
    }


async def fetch_vault_stress_test(vault_address: str, chain: str = "base") -> dict | None:
    """Simulate collateral price drops -5/-10/-20/-30% per Morpho market in a vault.

    For each market:
      - new_collateral = collateral_usd * (1 - drop)
      - market_bad_debt = max(0, total_borrow_usd - new_collateral)
      - vault_loss_share = (vault_supply / market_total_supply) * market_bad_debt
      - capped at vault_supply (can't lose more than allocated)

    Returns {drop_5/10/20/30: {bad_debt_usd, vault_loss_ratio}, vault_tvl_usd}.
    """
    chain_id = CHAIN_IDS.get(chain.lower(), 8453)
    query = """
    {
      vaults(where: { address_in: ["%s"], chainId_in: [%d] }) {
        items {
          state {
            totalAssetsUsd
            allocation {
              supplyAssetsUsd
              market {
                lltv
                collateralAsset { symbol }
                state {
                  supplyAssetsUsd
                  borrowAssetsUsd
                  collateralAssetsUsd
                }
              }
            }
          }
        }
      }
    }
    """ % (vault_address, chain_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(MORPHO_API_URL, json={"query": query})
            resp.raise_for_status()
            data = resp.json()
        items = (data.get("data") or {}).get("vaults", {}).get("items", [])
        if not items:
            return None
        st = items[0].get("state") or {}
        total_assets = float(st.get("totalAssetsUsd") or 0)
        allocations = st.get("allocation") or []
    except Exception as e:
        logger.error(f"Morpho stress test fetch failed for {vault_address}: {e}")
        return None

    if total_assets <= 0:
        return None

    drops = (0.05, 0.10, 0.20, 0.30)
    results: dict[str, dict] = {f"drop_{int(d*100)}": {"bad_debt_usd": 0.0,
                                                         "vault_loss_usd": 0.0}
                                  for d in drops}

    for a in allocations:
        vault_supply = float(a.get("supplyAssetsUsd") or 0)
        if vault_supply < 1:
            continue
        m = a.get("market") or {}
        ms = m.get("state") or {}
        collat_usd = float(ms.get("collateralAssetsUsd") or 0)
        borrow_usd = float(ms.get("borrowAssetsUsd") or 0)
        market_supply = float(ms.get("supplyAssetsUsd") or 0)
        if not m.get("collateralAsset") or market_supply <= 0:
            # Idle market — no collateral, no exposure
            continue

        # vault's pro-rata share of the market
        share = vault_supply / market_supply if market_supply > 0 else 0

        for d in drops:
            new_collat = collat_usd * (1 - d)
            market_bd = max(0.0, borrow_usd - new_collat)
            vault_loss = min(vault_supply, share * market_bd)
            results[f"drop_{int(d*100)}"]["bad_debt_usd"] += market_bd
            results[f"drop_{int(d*100)}"]["vault_loss_usd"] += vault_loss

    for k in results:
        results[k]["vault_loss_ratio"] = results[k]["vault_loss_usd"] / total_assets

    return {"vault_tvl_usd": total_assets, "scenarios": results}
