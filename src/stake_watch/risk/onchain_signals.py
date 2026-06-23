"""On-chain signal readers for Chainlink price feeds and L2 Sequencer status.

Uses raw eth_call via httpx to avoid heavy web3 instantiation costs.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

# Chainlink aggregator addresses for primary stablecoins
CHAINLINK_FEEDS: dict[tuple[str, str], str] = {
    # (chain, asset) → aggregator address
    ("ethereum", "USDC"): "0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6",
    ("ethereum", "USDT"): "0x3E7d1eAB13ad0104d2750B8863b489D65364e32D",
    # USDS feed not available on Chainlink yet — Sky governs via SSR
    ("base",     "USDC"): "0x7e860098F58bBFC8648a4311b374B1D669a2bc6B",
    ("base",     "USDT"): "0xf19d560eB8d2ADf07BD6D13ed03e1D11215721F9",
}

# Heartbeat (max acceptable time between updates) per feed, seconds.
# Stables on Chainlink are 24h heartbeated with 0.25% deviation trigger.
DEFAULT_HEARTBEAT = 86400
HEARTBEAT_OVERRIDES: dict[tuple[str, str], int] = {}

# L2 sequencer uptime feeds
SEQUENCER_FEEDS: dict[str, str] = {
    "base": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
}

# `latestRoundData()` selector
LATEST_ROUND_DATA_SELECTOR = "0xfeaf968c"


async def _eth_call(rpc_url: str, to: str, data: str) -> str | None:
    payload = {"jsonrpc": "2.0", "method": "eth_call",
               "params": [{"to": to, "data": data}, "latest"], "id": 1}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(rpc_url, json=payload)
            resp.raise_for_status()
            j = resp.json()
            return j.get("result")
    except Exception:
        return None


def _parse_latest_round_data(hex_result: str) -> tuple[int, int, int, int] | None:
    """Returns (answer, started_at, updated_at, age_seconds) or None on parse failure."""
    if not hex_result or not hex_result.startswith("0x"):
        return None
    data = hex_result[2:]
    if len(data) < 64 * 5:
        return None
    try:
        vals = [int(data[i*64:(i+1)*64], 16) for i in range(5)]
        # answer is int256 — convert if signed
        answer = vals[1] if vals[1] < 2**255 else vals[1] - 2**256
        started_at = vals[2]
        updated_at = vals[3]
        age = max(0, int(time.time()) - updated_at)
        return answer, started_at, updated_at, age
    except (ValueError, IndexError):
        return None


async def fetch_chainlink_price(rpc_url: str, chain: str, asset: str) -> dict | None:
    feed = CHAINLINK_FEEDS.get((chain.lower(), asset.upper()))
    if not feed:
        return None
    result = await _eth_call(rpc_url, feed, LATEST_ROUND_DATA_SELECTOR)
    parsed = _parse_latest_round_data(result or "")
    if not parsed:
        return None
    answer, _, updated_at, age = parsed
    heartbeat = HEARTBEAT_OVERRIDES.get((chain.lower(), asset.upper()), DEFAULT_HEARTBEAT)
    return {
        "price": answer / 1e8,  # all stables use 8 decimals
        "updated_at": updated_at,
        "age_seconds": age,
        "heartbeat_seconds": heartbeat,
        "is_stale": age > int(heartbeat * 1.1),
        "feed_address": feed,
    }


async def fetch_sequencer_status(rpc_url: str, chain: str) -> dict | None:
    feed = SEQUENCER_FEEDS.get(chain.lower())
    if not feed:
        return None
    result = await _eth_call(rpc_url, feed, LATEST_ROUND_DATA_SELECTOR)
    parsed = _parse_latest_round_data(result or "")
    if not parsed:
        return None
    answer, started_at, updated_at, _ = parsed
    is_up = answer == 0
    grace_seconds = max(0, int(time.time()) - started_at)
    return {
        "is_up": is_up,
        "status_since": started_at,
        "status_since_dt": datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat(),
        "seconds_in_status": grace_seconds,
        "updated_at": updated_at,
    }


async def fetch_solana_health(rpc_url: str) -> dict | None:
    """Returns recent slot rate + TPS averaged over last 5×60s samples."""
    payload = {"jsonrpc": "2.0", "id": 1,
               "method": "getRecentPerformanceSamples", "params": [5]}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(rpc_url, json=payload)
            resp.raise_for_status()
            samples = resp.json().get("result") or []
    except Exception:
        return None
    if not samples:
        return None
    total_slots = sum(s.get("numSlots", 0) for s in samples)
    total_period = sum(s.get("samplePeriodSecs", 0) for s in samples)
    total_non_vote = sum(s.get("numNonVoteTransactions", 0) for s in samples)
    if total_period <= 0:
        return None
    slot_rate = total_slots / total_period  # slots / sec, healthy ≈ 2.5
    tps_non_vote = total_non_vote / total_period
    return {
        "slot_rate": slot_rate,
        "tps_non_vote": tps_non_vote,
        "latest_slot": samples[0].get("slot"),
        "samples": len(samples),
        # Health bands per spec §3.7 chain-stability
        "degraded": slot_rate < 2.0,
        "critical": slot_rate < 1.5,
    }


# Pyth Network Hermes API (off-chain price feed updates)
PYTH_HERMES_URL = "https://hermes.pyth.network/v2/updates/price/latest"
PYTH_FEED_IDS: dict[str, str] = {
    # asset → Pyth feed id (without 0x prefix)
    "USDC": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    "USDT": "2b89b9dc8fdf9f34709a5b106b472f0f39bb6ca9ce04b0fd7f2e971688e2e53b",
}


async def fetch_pyth_price(assets: list[str]) -> dict[str, dict] | None:
    """Returns {asset: {price, publish_time, age_seconds}} via Hermes API."""
    feed_ids = [(a, PYTH_FEED_IDS[a]) for a in assets if a in PYTH_FEED_IDS]
    if not feed_ids:
        return None
    params = [("ids[]", f"0x{fid}") for _, fid in feed_ids]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(PYTH_HERMES_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None
    out: dict[str, dict] = {}
    parsed = data.get("parsed", [])
    now = int(time.time())
    by_id = {e["id"]: e for e in parsed}
    for asset, fid in feed_ids:
        e = by_id.get(fid) or by_id.get("0x" + fid)
        if not e:
            continue
        p = e.get("price") or {}
        try:
            price = int(p["price"]) * (10 ** int(p["expo"]))
            publish = int(p["publish_time"])
        except (KeyError, ValueError, TypeError):
            continue
        out[asset] = {
            "price": price,
            "publish_time": publish,
            "age_seconds": max(0, now - publish),
            "feed_id": fid,
        }
    return out or None
