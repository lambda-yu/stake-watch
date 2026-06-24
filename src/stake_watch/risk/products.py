"""Product registry: primary (chain, asset) for each protocol.

Drives the protocol-level risk summary. Used by:
- api/routes/protocols.py for `_to_dict()` enrichment
- risk/protocol_status.py for the live evaluation orchestrator
- risk/protocol_risk_monitor.py for the periodic alert sweep

Lives in the risk module so domain logic doesn't reverse-import from routes/.
"""
from __future__ import annotations

PRIMARY_PRODUCT: dict[str, tuple[str, str]] = {
    "aave_v3_base":               ("base",     "USDC"),
    "sky_susds":                  ("ethereum", "USDS"),
    "compound_v3_usdc":           ("base",     "USDC"),
    "morpho_steakhouse_usdc":     ("base",     "USDC"),
    "morpho_gauntlet_usdc_prime": ("base",     "USDC"),
    "morpho_pangolins_usdc":      ("base",     "USDC"),
    "morpho_gauntlet_rwa_usdc":   ("ethereum", "USDC"),
    "fluid_usdc":                 ("ethereum", "USDC"),
    "jupiter_lend":               ("solana",   "USDC"),
    "kamino_usdc":                ("solana",   "USDC"),
}


def primary_for(protocol_name: str, fallback_chain: str,
                 fallback_asset: str = "USDC") -> tuple[str, str]:
    """Return (chain, asset) for protocol, with fallback when unknown."""
    return PRIMARY_PRODUCT.get(protocol_name, (fallback_chain, fallback_asset))
