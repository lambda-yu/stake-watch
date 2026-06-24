"""GET endpoints for stored wallet positions."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from stake_watch.api.deps import get_config_store, get_storage
from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

router = APIRouter()


def _to_dict(p) -> dict:
    return {
        "chain": p.chain.value if hasattr(p.chain, "value") else p.chain,
        "protocol": p.protocol,
        "wallet": p.wallet,
        "asset": p.asset,
        "position_type": p.position_type.value if hasattr(p.position_type, "value") else p.position_type,
        "amount": str(p.amount),
        "value_usd": str(p.value_usd),
        "apy": p.apy,
        "ltv": p.ltv,
        "health_factor": p.health_factor,
        "vault_version": p.vault_version,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("")
async def list_positions(wallet: str | None = None,
                          storage: Storage = Depends(get_storage),
                          store: ConfigStore = Depends(get_config_store)):
    """Return latest positions across configured wallets.

    `?wallet=0x...` limits to one wallet; otherwise aggregates all configured.
    """
    if wallet:
        wallets = [wallet]
    else:
        ws = await store.list_wallets()
        wallets = [w.address for w in ws]

    out: list[dict] = []
    for w in wallets:
        if not w:
            continue
        positions = await storage.get_latest_positions(w)
        out.extend(_to_dict(p) for p in positions)
    return {"positions": out, "count": len(out)}
