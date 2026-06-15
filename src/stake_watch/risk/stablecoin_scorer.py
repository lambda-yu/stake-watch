from __future__ import annotations
from pydantic import BaseModel


class ScoreInput(BaseModel):
    price: float = 1.0
    deviation: float = 0.0
    supply_change_24h_pct: float = 0.0
    supply_change_7d_pct: float = 0.0
    cex_spread_pct: float = 0.0
    dex_liquidity_score: float = 0.0    # placeholder, 0 = no data
    reserve_score: float = 0.0          # placeholder, 0 = no data
    issuer_score: float = 0.0           # placeholder, 0 = no data
    is_blacklisted: bool = False
    cross_chain_verified: bool = True
    cross_chain_risk_premium: int = 0


class ScoreResult(BaseModel):
    score: float       # 0-100
    level: str         # safe | watch | caution | danger | critical
    hard_trigger: str | None = None
    breakdown: dict = {}


WEIGHTS = {
    "depeg": 0.25,
    "dex_liquidity": 0.15,
    "redemption": 0.15,
    "reserve": 0.20,
    "issuer": 0.10,
    "contract": 0.10,
    "cross_chain": 0.05,
}

HARD_TRIGGERS = [
    ("price_below_098", lambda i: i.price < 0.98),
    ("wallet_blacklisted", lambda i: i.is_blacklisted),
    ("cex_spread_above_2pct", lambda i: i.cex_spread_pct > 2.0),
]


def _level(score: float) -> str:
    if score < 20:
        return "safe"
    if score < 35:
        return "watch"
    if score < 50:
        return "caution"
    if score < 70:
        return "danger"
    return "critical"


class StablecoinScorer:
    def score(self, inp: ScoreInput) -> ScoreResult:
        # Check hard triggers first
        for name, check in HARD_TRIGGERS:
            if check(inp):
                return ScoreResult(score=100, level="critical", hard_trigger=name)

        breakdown: dict[str, float] = {}

        # Depeg: deviation scaled to 0-100 (0.5% = 50, 1% = 100)
        breakdown["depeg"] = min(inp.deviation / 0.01 * 100, 100)

        # DEX liquidity: placeholder
        breakdown["dex_liquidity"] = inp.dex_liquidity_score

        # Redemption: supply change scaled (3%/day = 50, 5% = 80, 10% = 100)
        abs_change = abs(min(inp.supply_change_24h_pct, 0))
        breakdown["redemption"] = min(abs_change / 10 * 100, 100) if abs_change > 0 else 0

        # Reserve: placeholder
        breakdown["reserve"] = inp.reserve_score

        # Issuer: placeholder
        breakdown["issuer"] = inp.issuer_score

        # Contract risk: blacklist = 100 (handled in hard trigger), else CEX spread contributes
        contract_score = 0.0
        if inp.cex_spread_pct > 0.5:
            contract_score = min(inp.cex_spread_pct / 2.0 * 100, 100)
        breakdown["contract"] = contract_score

        # Cross-chain: unverified = 100, bridged premium scaled
        if not inp.cross_chain_verified:
            breakdown["cross_chain"] = 100
        else:
            breakdown["cross_chain"] = min(inp.cross_chain_risk_premium, 100)

        # Renormalize weights over dimensions that have data (non-placeholder = > 0
        # or always-available dimensions). Placeholder dimensions (dex_liquidity,
        # reserve, issuer) with 0 score are excluded so their weight doesn't
        # silently dilute the composite score until real data sources are wired in.
        placeholder_keys = {"dex_liquidity", "reserve", "issuer"}
        active_keys = [
            k for k in WEIGHTS
            if k not in placeholder_keys or breakdown[k] > 0
        ]
        active_weight = sum(WEIGHTS[k] for k in active_keys)
        if active_weight > 0:
            weighted = sum(breakdown[k] * WEIGHTS[k] for k in active_keys) / active_weight
        else:
            weighted = 0.0

        return ScoreResult(
            score=round(weighted, 1),
            level=_level(weighted),
            breakdown=breakdown,
        )
