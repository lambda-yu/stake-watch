"""Sky sUSDS on-chain reader for SSR (Sky Savings Rate) and TVL.

The Sky Savings Rate contract exposes `ssr()` returning the per-second rate in RAY (1e27).
APY = (ssr / 1e27) ^ (seconds_per_year) - 1
"""
from __future__ import annotations

from decimal import Decimal, getcontext

from web3 import AsyncWeb3, AsyncHTTPProvider

from stake_watch.collectors.sky.abi import SUSDS_ABI, SUSDS_ADDRESS

getcontext().prec = 50

RAY = Decimal(10) ** 27
SECONDS_PER_YEAR = 365 * 86400


async def fetch_sky_susds_data(rpc_url: str) -> dict | None:
    """Read SSR and TVL from sUSDS contract.

    Returns {asset: "USDS", apy (%), tvl_usd} or None on failure.
    """
    try:
        w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        contract = w3.eth.contract(
            address=w3.to_checksum_address(SUSDS_ADDRESS), abi=SUSDS_ABI
        )
        ssr_raw = await contract.functions.ssr().call()
        total_shares = await contract.functions.totalSupply().call()
        total_assets = await contract.functions.convertToAssets(total_shares).call()
    except Exception:
        return None

    per_second_rate = Decimal(ssr_raw) / RAY
    if per_second_rate <= 0:
        return None
    apy = float(per_second_rate ** SECONDS_PER_YEAR - Decimal(1)) * 100

    tvl_usd = float(Decimal(total_assets) / Decimal(10) ** 18)  # USDS = $1
    return {"asset": "USDS", "apy": apy, "tvl_usd": tvl_usd}
