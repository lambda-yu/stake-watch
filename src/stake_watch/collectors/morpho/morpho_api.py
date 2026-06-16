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

    Returns: {tvl_usd, net_apy, apy, name, asset, symbol} or None.
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
          state { totalAssetsUsd netApy apy }
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
        return {
            "name": v.get("name"),
            "asset": v.get("asset", {}).get("symbol", "USDC"),
            "symbol": v.get("symbol"),
            "tvl_usd": float(st.get("totalAssetsUsd") or 0),
            "apy": float(st.get("apy") or 0) * 100,
            "net_apy": float(st.get("netApy") or 0) * 100,
        }
    except Exception as e:
        logger.error(f"Morpho API error for {vault_address}: {e}")
        return None
