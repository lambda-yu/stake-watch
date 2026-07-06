"""Tests for the interactive Telegram command bot."""
from __future__ import annotations

from datetime import datetime, timezone

from stake_watch.alerts.bot_commands import (
    format_help,
    format_protocol_detail,
)


# ---------- format_help ----------

def test_format_help_lists_all_four_commands():
    text = format_help()
    for cmd in ("/help", "/protocols", "/compare", "/protocol <"):
        assert cmd in text, f"missing {cmd} in help output"


def _make_stats(ts: datetime | None = None):
    """Cheap stand-in — the formatter only reads .timestamp."""
    class _S:
        timestamp = ts
    return _S()


def test_format_protocol_detail_full_layout():
    protocol = {
        "name": "Aave",
        "chain": "Ethereum",
        "enabled": True,
        "safety_score": 85,
        "risk_scores": {"liquidity": 90, "smart_contract": 80, "governance": 85},
    }
    chains_breakdown = [
        {
            "chain": "Ethereum",
            "by_asset": {
                "USDC": {"apy": 4.12, "tvl_usd": 1.2e9},
                "USDT": {"apy": 3.98, "tvl_usd": 8.9e8},
            },
        },
        {
            "chain": "Base",
            "by_asset": {"USDC": {"apy": 5.20, "tvl_usd": 1.2e8}},
        },
    ]
    stats = _make_stats(datetime(2026, 7, 3, 6, 20, tzinfo=timezone.utc))

    out = format_protocol_detail(
        protocol=protocol,
        chains_breakdown=chains_breakdown,
        stats=stats,
        tz_offset=8,
    )

    assert "📋 Aave" in out
    assert "链: Ethereum" in out
    assert "状态: 启用 ✓" in out
    assert "Safety Score: 85" in out
    assert "USDC" in out and "4.12" in out and "$1.20B" in out
    assert "USDT" in out and "3.98" in out and "$890.0M" in out
    assert "Base" in out
    assert "5.20" in out and "$120.0M" in out
    assert "liquidity 90" in out
    assert "smart_contract 80" in out
    assert "governance 85" in out
    assert "2026-07-03 14:20 UTC+8" in out
    # Order semantics: USDC before USDT, primary chain (Ethereum) before Base
    assert out.index("USDC") < out.index("USDT")
    assert out.index("Ethereum") < out.index("Base")
