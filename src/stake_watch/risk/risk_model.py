"""Stake Watch Risk Model v2.

Implements the 8-dimension weighted risk scoring framework from the user spec.

Score scale: 0-100, higher = riskier.
Level: A (0-20) / B (20-30) / C (30-40) / D (40-55) / E (>55).

Each protocol-chain-asset tuple has curated per-dimension scores. When live data
is available (utilization, bad_debt, oracle_deviation, etc.) it can override
dimension scores via `merge_live_signals()`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DIMENSIONS: list[tuple[str, str, float]] = [
    ("contract",         "协议与合约",   0.20),
    ("market",           "市场与坏账",   0.20),
    ("liquidity",        "提现流动性",   0.15),
    ("collateral_oracle","抵押品/预言机", 0.15),
    ("governance",       "管理与治理",   0.10),
    ("stablecoin",       "稳定币资产",   0.08),
    ("chain",            "链与基础设施", 0.07),
    ("yield",            "收益异常",     0.05),
]
DIM_KEYS = [k for k, _, _ in DIMENSIONS]
DIM_WEIGHTS = {k: w for k, _, w in DIMENSIONS}
DIM_LABELS = {k: l for k, l, _ in DIMENSIONS}


# Per-product curated dimension scores (0-100; higher = riskier).
# Keyed by (protocol_name, chain, asset).
PRODUCT_RISK: dict[tuple[str, str, str], dict[str, float]] = {
    # Aave V3
    ("aave_v3_base", "ethereum", "USDC"): {"contract": 10, "market": 18, "liquidity": 12, "collateral_oracle": 18, "governance": 10, "stablecoin": 12, "chain": 5,  "yield": 10},
    ("aave_v3_base", "ethereum", "USDT"): {"contract": 10, "market": 22, "liquidity": 15, "collateral_oracle": 20, "governance": 10, "stablecoin": 18, "chain": 5,  "yield": 10},
    ("aave_v3_base", "base",     "USDC"): {"contract": 10, "market": 22, "liquidity": 18, "collateral_oracle": 22, "governance": 10, "stablecoin": 12, "chain": 15, "yield": 12},
    # Compound V3
    ("compound_v3_usdc", "ethereum", "USDC"): {"contract": 12, "market": 20, "liquidity": 15, "collateral_oracle": 22, "governance": 12, "stablecoin": 12, "chain": 5,  "yield": 15},
    ("compound_v3_usdc", "ethereum", "USDT"): {"contract": 12, "market": 24, "liquidity": 18, "collateral_oracle": 25, "governance": 12, "stablecoin": 18, "chain": 5,  "yield": 15},
    ("compound_v3_usdc", "base",     "USDC"): {"contract": 12, "market": 32, "liquidity": 30, "collateral_oracle": 25, "governance": 12, "stablecoin": 12, "chain": 15, "yield": 25},
    # Morpho Vaults
    ("morpho_steakhouse_usdc",    "base",     "USDC"): {"contract": 12, "market": 22, "liquidity": 20, "collateral_oracle": 22, "governance": 20, "stablecoin": 12, "chain": 15, "yield": 18},
    ("morpho_gauntlet_usdc_prime","base",     "USDC"): {"contract": 12, "market": 22, "liquidity": 20, "collateral_oracle": 22, "governance": 20, "stablecoin": 12, "chain": 15, "yield": 18},
    ("morpho_pangolins_usdc",     "base",     "USDC"): {"contract": 12, "market": 32, "liquidity": 28, "collateral_oracle": 30, "governance": 28, "stablecoin": 12, "chain": 15, "yield": 30},
    ("morpho_gauntlet_rwa_usdc",  "ethereum", "USDC"): {"contract": 12, "market": 32, "liquidity": 30, "collateral_oracle": 45, "governance": 25, "stablecoin": 12, "chain": 5,  "yield": 35},
    # Sky / sUSDS
    ("sky_susds", "ethereum", "USDS"): {"contract": 15, "market": 18, "liquidity": 18, "collateral_oracle": 22, "governance": 18, "stablecoin": 20, "chain": 5, "yield": 12},
    # Fluid
    ("fluid_usdc", "ethereum", "USDC"): {"contract": 22, "market": 28, "liquidity": 28, "collateral_oracle": 28, "governance": 22, "stablecoin": 12, "chain": 5,  "yield": 30},
    ("fluid_usdc", "ethereum", "USDT"): {"contract": 22, "market": 32, "liquidity": 32, "collateral_oracle": 30, "governance": 22, "stablecoin": 18, "chain": 5,  "yield": 32},
    ("fluid_usdc", "base",     "USDC"): {"contract": 22, "market": 38, "liquidity": 38, "collateral_oracle": 32, "governance": 22, "stablecoin": 12, "chain": 15, "yield": 35},
    # Jupiter Lend
    ("jupiter_lend", "solana", "USDC"): {"contract": 25, "market": 28, "liquidity": 28, "collateral_oracle": 30, "governance": 25, "stablecoin": 12, "chain": 18, "yield": 25},
    ("jupiter_lend", "solana", "USDT"): {"contract": 25, "market": 35, "liquidity": 35, "collateral_oracle": 32, "governance": 25, "stablecoin": 18, "chain": 18, "yield": 30},
    # Kamino
    ("kamino_usdc",  "solana", "USDC"): {"contract": 22, "market": 30, "liquidity": 30, "collateral_oracle": 32, "governance": 22, "stablecoin": 12, "chain": 18, "yield": 28},
    ("kamino_usdc",  "solana", "USDT"): {"contract": 22, "market": 38, "liquidity": 38, "collateral_oracle": 34, "governance": 22, "stablecoin": 18, "chain": 18, "yield": 32},
}


# Curated per-dimension explanation notes (short).
DIM_NOTES: dict[tuple[str, str], str] = {
    # contract
    ("aave_v3_base", "contract"):              "Aave V3 多轮审计 (OZ/ToB/Certora)，主网 2 年+ 无重大事故",
    ("compound_v3_usdc", "contract"):          "Compound V3 (Comet) 单基础资产设计，审计充分",
    ("sky_susds", "contract"):                 "Sky 由 MakerDAO 演化而来，核心 DSS 系统 8 年+ 运行",
    ("morpho_steakhouse_usdc", "contract"):    "Morpho Blue 核心不可升级；ERC-4626 Vault 标准化",
    ("morpho_gauntlet_usdc_prime", "contract"):"Morpho Blue 核心不可升级；Gauntlet 风控成熟",
    ("morpho_pangolins_usdc", "contract"):     "Morpho Blue 核心不可升级；Pangolins 较新",
    ("morpho_gauntlet_rwa_usdc", "contract"):  "Morpho Blue 核心不可升级；Gauntlet RWA 复杂度高",
    ("fluid_usdc", "contract"):                "Instadapp Fluid 2024 上线，复杂 Smart Debt/Col 机制",
    ("jupiter_lend", "contract"):              "Jupiter Lend 2025 上线，OtterSec/Sec3 审计",
    ("kamino_usdc", "contract"):               "Kamino 2023 起，K-Lend 2024 上线，OtterSec/Halborn 审计",
    # market
    ("aave_v3_base", "market"):                "共享流动池，参数保守，历史无显著坏债",
    ("compound_v3_usdc", "market"):            "单基础资产模式，坏账隔离性较好",
    ("sky_susds", "market"):                   "由 USDS 协议盈余补贴，市场风险低",
    ("morpho_steakhouse_usdc", "market"):      "Steakhouse curator 偏保守，配置蓝筹市场",
    ("morpho_gauntlet_usdc_prime", "market"):  "Gauntlet 主动监控，Prime 等级抵押品质量高",
    ("morpho_pangolins_usdc", "market"):       "Pangolins 策略更激进，单市场坏账敞口大",
    ("morpho_gauntlet_rwa_usdc", "market"):    "RWA 抵押品流动性差，市场清算路径不确定",
    ("fluid_usdc", "market"):                  "Smart Debt/Col 创新机制，市场风险模型新",
    ("jupiter_lend", "market"):                "统一流动性层 + 提款平滑，规模 $400M+",
    ("kamino_usdc", "market"):                 "Main Market 多抵押品共享，4 月曾达 100% 利用率",
    # liquidity
    ("aave_v3_base", "liquidity"):             "USDC 池深，可用流动性充足",
    ("compound_v3_usdc", "liquidity"):         "Compound 提款流畅，规模大",
    ("sky_susds", "liquidity"):                "sUSDS→USDS 即时；USDS→USDC 走 PSM 1:1",
    ("morpho_steakhouse_usdc", "liquidity"):   "Base TVL 充足；大额提款需 Morpho 市场再平衡",
    ("morpho_gauntlet_usdc_prime", "liquidity"):"Base TVL 大，提款体验较好",
    ("morpho_pangolins_usdc", "liquidity"):    "TVL 较小，大额提款滑点高",
    ("morpho_gauntlet_rwa_usdc", "liquidity"): "RWA 不可即时清算，赎回周期长",
    ("fluid_usdc", "liquidity"):               "复杂的 Liquidity Layer，提款路径多样",
    ("jupiter_lend", "liquidity"):             "提款平滑机制可能延后到账",
    ("kamino_usdc", "liquidity"):              "高利用率时提款受限",
    # collateral_oracle
    ("aave_v3_base", "collateral_oracle"):     "蓝筹抵押品 + Chainlink + 偏离断路器",
    ("compound_v3_usdc", "collateral_oracle"): "Chainlink + sequencer uptime feed",
    ("sky_susds", "collateral_oracle"):        "USDS 由治理设定锚定，不依赖外部价格喂价",
    ("morpho_steakhouse_usdc", "collateral_oracle"):    "依赖底层 Morpho 各市场 Chainlink/Pyth",
    ("morpho_gauntlet_usdc_prime", "collateral_oracle"):"底层市场喂价；Gauntlet 监控异常",
    ("morpho_pangolins_usdc", "collateral_oracle"):     "底层市场喂价；策略激进需关注 Oracle 偏差",
    ("morpho_gauntlet_rwa_usdc", "collateral_oracle"):  "Chainlink + RWA 估值数据，定价透明度低",
    ("fluid_usdc", "collateral_oracle"):       "Chainlink 主导，部分用 DEX 中间价",
    ("jupiter_lend", "collateral_oracle"):     "Pyth + Switchboard 双源",
    ("kamino_usdc", "collateral_oracle"):      "Pyth + Switchboard",
    # governance
    ("aave_v3_base", "governance"):            "Aave DAO 链上治理 + Guardian 紧急暂停",
    ("compound_v3_usdc", "governance"):        "COMP 治理 + Timelock + Guardian",
    ("sky_susds", "governance"):               "Sky 治理 + GSM Delay，SSR 由治理设定",
    ("morpho_steakhouse_usdc", "governance"):  "Steakhouse 作为 curator 调配 Vault 分配",
    ("morpho_gauntlet_usdc_prime", "governance"):"Gauntlet 作为 curator + 主动风控团队",
    ("morpho_pangolins_usdc", "governance"):   "Pangolins 团队规模小，治理透明度有限",
    ("morpho_gauntlet_rwa_usdc", "governance"):"Gauntlet curator 模式同 Prime",
    ("fluid_usdc", "governance"):              "Instadapp 团队/DAO 控制，去中心化中等",
    ("jupiter_lend", "governance"):            "Jupiter DAO + JUP 治理，较新",
    ("kamino_usdc", "governance"):             "Kamino DAO + KMNO 治理",
}

ASSET_DEFAULT_STABLE = {"USDC": 12, "USDT": 18, "USDS": 20, "USD0": 30, "USD1": 30}
CHAIN_DEFAULT = {"ethereum": 5, "base": 15, "solana": 18, "bsc": 22}


# Curated authoritative total risk score per product (from spec §5).
# When present, takes precedence over the weighted dim sum.
PRODUCT_TOTAL: dict[tuple[str, str, str], float] = {
    ("aave_v3_base",              "ethereum", "USDC"): 17,
    ("aave_v3_base",              "ethereum", "USDT"): 20,
    ("aave_v3_base",              "base",     "USDC"): 25,
    ("sky_susds",                 "ethereum", "USDS"): 21,
    ("compound_v3_usdc",          "ethereum", "USDC"): 21,
    ("compound_v3_usdc",          "ethereum", "USDT"): 24,
    ("compound_v3_usdc",          "base",     "USDC"): 31,
    ("morpho_gauntlet_usdc_prime","base",     "USDC"): 24,
    ("morpho_steakhouse_usdc",    "base",     "USDC"): 24,
    ("morpho_pangolins_usdc",     "base",     "USDC"): 28,
    ("morpho_gauntlet_rwa_usdc",  "ethereum", "USDC"): 33,
    ("fluid_usdc",                "ethereum", "USDC"): 28,
    ("fluid_usdc",                "ethereum", "USDT"): 31,
    ("fluid_usdc",                "base",     "USDC"): 34,
    ("jupiter_lend",              "solana",   "USDC"): 30,
    ("jupiter_lend",              "solana",   "USDT"): 36,
    ("kamino_usdc",               "solana",   "USDC"): 30,
    ("kamino_usdc",               "solana",   "USDT"): 38,
}


@dataclass
class RiskResult:
    total: float       # 0-100
    level: str         # A/B/C/D/E
    dimensions: dict[str, dict]   # key → {score, weight, label, notes, source}
    adjusted_yield_linear: float
    adjusted_yield_exp: float
    raw_apy: float
    veto_flags: list[str]
    live_signals: dict   # signals that were applied (or empty)


def _level(total: float) -> str:
    if total <= 20: return "A"
    if total <= 30: return "B"
    if total <= 40: return "C"
    if total <= 55: return "D"
    return "E"


def _default_dims(protocol: str, chain: str, asset: str) -> dict[str, float]:
    """Best-effort defaults when product isn't in PRODUCT_RISK table."""
    base = {
        "contract": 25, "market": 30, "liquidity": 28, "collateral_oracle": 30,
        "governance": 25, "stablecoin": ASSET_DEFAULT_STABLE.get(asset.upper(), 25),
        "chain": CHAIN_DEFAULT.get(chain.lower(), 20), "yield": 25,
    }
    return base


def get_dim_scores(protocol: str, chain: str, asset: str) -> dict[str, float]:
    key = (protocol, chain.lower(), asset.upper())
    dims = PRODUCT_RISK.get(key)
    if dims:
        return dict(dims)
    # Fallback: substitute stablecoin + chain into a generic profile
    dims = _default_dims(protocol, chain, asset)
    return dims


def _utilization_to_score(util: float) -> tuple[float, str]:
    """Map utilization (0-1) to liquidity-dim risk score per §3.3."""
    if util < 0.65: return 5,   f"利用率 {util*100:.1f}%，提现宽裕"
    if util < 0.75: return 15,  f"利用率 {util*100:.1f}%，提款流畅"
    if util < 0.85: return 30,  f"利用率 {util*100:.1f}%，进入紧张区间"
    if util < 0.92: return 55,  f"利用率 {util*100:.1f}%，大额提款滑点高"
    if util < 0.97: return 80,  f"利用率 {util*100:.1f}%，接近提款冻结"
    return 100,                 f"利用率 {util*100:.1f}%，提款基本被锁定"


def _withdrawable_ratio_to_score(ratio: float) -> tuple[float, str]:
    """Map available-liquidity / total-supply ratio per §3.3."""
    if ratio > 0.50: return 5,   f"可提现 {ratio*100:.1f}%，深度充足"
    if ratio > 0.30: return 15,  f"可提现 {ratio*100:.1f}%，宽裕"
    if ratio > 0.15: return 35,  f"可提现 {ratio*100:.1f}%，进入紧张区间"
    if ratio > 0.05: return 65,  f"可提现 {ratio*100:.1f}%，大额提款受限"
    return 100,                  f"可提现 {ratio*100:.1f}%，几乎无法提现"


def _withdraw_simulation_bump(ratio: float) -> tuple[int, list[str], bool]:
    """Per §3.3 - withdrawal simulation adjustment.

    Returns (extra_score, notes, withdraw_10_failed).
    10% sim fail = +40, 50% fail = +20, 100% fail = +10. Stack additively.
    """
    extra = 0
    notes = []
    w10_failed = ratio < 0.10
    if ratio < 0.10:
        extra += 40
        notes.append("10% 提现模拟失败")
    if ratio < 0.50:
        extra += 20
        notes.append("50% 提现模拟失败")
    if ratio < 1.00:
        extra += 10
        notes.append("100% 提现模拟失败")
    return extra, notes, w10_failed


def _apy_premium_to_score(premium_pct: float) -> tuple[float, str]:
    """Map APY超过同类中位数的差值（百分点）per §3.8."""
    if premium_pct < 0.5: return 5,   f"APY 接近同类中位数 (+{premium_pct:.2f}pp)"
    if premium_pct < 1.5: return 20,  f"APY 略高于同类 (+{premium_pct:.2f}pp)"
    if premium_pct < 3.0: return 45,  f"APY 高于同类 (+{premium_pct:.2f}pp)，关注可持续性"
    if premium_pct < 5.0: return 70,  f"APY 显著高于同类 (+{premium_pct:.2f}pp)，疑似激励"
    return 100,                       f"APY 异常高 (+{premium_pct:.2f}pp)，风险信号"


def _cap_usage_to_score(usage: float, kind: str) -> tuple[float, str]:
    """Map supply/borrow cap usage (0-1) to market-dim impact."""
    if usage < 0.6:  return 5,   f"{kind} cap 使用率 {usage*100:.0f}%，宽松"
    if usage < 0.8:  return 20,  f"{kind} cap 使用率 {usage*100:.0f}%，正常"
    if usage < 0.92: return 50,  f"{kind} cap 使用率 {usage*100:.0f}%，紧张"
    if usage < 0.98: return 75,  f"{kind} cap 使用率 {usage*100:.0f}%，接近上限"
    return 100,                  f"{kind} cap 已耗尽 ({usage*100:.0f}%)"


def evaluate(protocol: str, chain: str, asset: str, apy: float | None = None,
             live_signals: dict | None = None) -> RiskResult:
    """Compute risk score for a (protocol, chain, asset) product.

    live_signals (optional) overrides curated dimension scores. Recognized keys:
      - utilization: 0-1 (overrides liquidity dim)
      - withdrawable_ratio: 0-1 (overrides liquidity dim, takes worst-of with utilization)
      - bad_debt_ratio: 0-1 (overrides market dim)
      - oracle_deviation: 0-1 (overrides collateral_oracle dim)
      - apy_premium_pct: float (overrides yield dim) - APY above peer median, percentage points
      - apy_inverted: bool (forces market dim to >=70 if true) - supply>=borrow
      - supply_cap_usage / borrow_cap_usage: 0-1 (market dim worst-of)
      - tvl_drop_24h: 0-1 (market dim, big drops critical)
    """
    live_signals = live_signals or {}
    dims = get_dim_scores(protocol, chain, asset)
    dim_sources = {k: "curated" for k in dims}
    dim_notes_override: dict[str, str] = {}

    # --- liquidity dim: pick worst of utilization / withdrawable_ratio + simulation bump ---
    liq_score, liq_note = None, None
    sim_extra = 0
    sim_notes: list[str] = []
    withdraw_10_failed = False
    if "utilization" in live_signals:
        liq_score, liq_note = _utilization_to_score(float(live_signals["utilization"]))
    if "withdrawable_ratio" in live_signals:
        wr = float(live_signals["withdrawable_ratio"])
        s, n = _withdrawable_ratio_to_score(wr)
        if liq_score is None or s > liq_score:
            liq_score, liq_note = s, n
        sim_extra, sim_notes, withdraw_10_failed = _withdraw_simulation_bump(wr)
    if liq_score is not None:
        final_score = min(100, liq_score + sim_extra)
        dims["liquidity"] = final_score
        dim_sources["liquidity"] = "live"
        suffix = f" · {', '.join(sim_notes)}" if sim_notes else ""
        dim_notes_override["liquidity"] = f"{liq_note}{suffix}"
    if withdraw_10_failed:
        live_signals["withdraw_10_failed"] = True

    # --- market dim: pick worst of bad_debt / apy_inverted / caps / tvl_drop ---
    market_score, market_note = None, None
    if "bad_debt_ratio" in live_signals:
        ratio = float(live_signals["bad_debt_ratio"])
        if ratio < 0.0001:    s, n = 0,   "未发现坏账"
        elif ratio < 0.0005:  s, n = 10,  f"坏账率 {ratio*100:.3f}%，可忽略"
        elif ratio < 0.002:   s, n = 30,  f"坏账率 {ratio*100:.3f}%，需关注"
        elif ratio < 0.005:   s, n = 50,  f"坏账率 {ratio*100:.3f}%，已偏高"
        elif ratio < 0.01:    s, n = 70,  f"坏账率 {ratio*100:.3f}%，警戒"
        else:                 s, n = 100, f"坏账率 {ratio*100:.3f}%，严重"
        if market_score is None or s > market_score:
            market_score, market_note = s, n
    if live_signals.get("apy_inverted"):
        s, n = 80, "Supply APY ≥ Borrow APY，死亡螺旋信号"
        if market_score is None or s > market_score:
            market_score, market_note = s, n
    for kind, key in (("Supply", "supply_cap_usage"), ("Borrow", "borrow_cap_usage")):
        if key in live_signals:
            s, n = _cap_usage_to_score(float(live_signals[key]), kind)
            if market_score is None or s > market_score:
                market_score, market_note = s, n
    if "tvl_drop_24h" in live_signals:
        drop = float(live_signals["tvl_drop_24h"])
        if drop > 0.30:   s, n = 100, f"TVL 24h 跌幅 {drop*100:.1f}%，严重外流"
        elif drop > 0.15: s, n = 70,  f"TVL 24h 跌幅 {drop*100:.1f}%，触发警戒"
        elif drop > 0.08: s, n = 40,  f"TVL 24h 跌幅 {drop*100:.1f}%，关注资金外流"
        else:             s, n = None, None
        if s is not None and (market_score is None or s > market_score):
            market_score, market_note = s, n
    if market_score is not None:
        dims["market"] = market_score
        dim_sources["market"] = "live"
        dim_notes_override["market"] = market_note

    # --- collateral_oracle dim ---
    oracle_score, oracle_note = None, None
    if "oracle_deviation" in live_signals:
        dev = float(live_signals["oracle_deviation"])
        if dev < 0.003: s, n = 5,   f"Oracle 偏差 {dev*100:.2f}%"
        elif dev < 0.01: s, n = 20,  f"Oracle 偏差 {dev*100:.2f}%，正常波动"
        elif dev < 0.02: s, n = 50,  f"Oracle 偏差 {dev*100:.2f}%，注意"
        elif dev < 0.05: s, n = 80,  f"Oracle 偏差 {dev*100:.2f}%，警戒"
        else:            s, n = 100, f"Oracle 偏差 {dev*100:.2f}%，已触发否决"
        if oracle_score is None or s > oracle_score:
            oracle_score, oracle_note = s, n
    if "oracle_staleness_seconds" in live_signals:
        age = int(live_signals["oracle_staleness_seconds"])
        heartbeat = int(live_signals.get("oracle_heartbeat_seconds", 86400))
        ratio = age / heartbeat if heartbeat > 0 else 0
        if ratio < 1.0:    s, n = 5,   f"Oracle 新鲜（{age//60}分钟前更新）"
        elif ratio < 1.1:  s, n = 25,  f"Oracle 接近心跳上限（{age//60}分钟，心跳 {heartbeat//3600}h）"
        elif ratio < 1.5:  s, n = 60,  f"Oracle 已超心跳（{age//60}分钟 > {heartbeat//60}）"
        else:              s, n = 100, f"Oracle 严重停滞（{age//3600}小时未更新）"
        if oracle_score is None or s > oracle_score:
            oracle_score, oracle_note = s, n
    if oracle_score is not None:
        dims["collateral_oracle"] = oracle_score
        dim_sources["collateral_oracle"] = "live"
        dim_notes_override["collateral_oracle"] = oracle_note

    # --- chain dim: Sequencer / Solana / RPC status ---
    if "sequencer_down" in live_signals and live_signals["sequencer_down"]:
        dims["chain"] = 100
        dim_sources["chain"] = "live"
        secs = int(live_signals.get("sequencer_down_seconds", 0))
        dim_notes_override["chain"] = f"L2 Sequencer 已停机 {secs//60} 分钟，所有交易被锁"
    elif live_signals.get("sequencer_recent_recovery"):
        dims["chain"] = max(40, dims.get("chain", 25))
        dim_sources["chain"] = "live"
        dim_notes_override["chain"] = "Sequencer 刚恢复，仍处于宽限期，建议谨慎操作"
    elif "solana_slot_rate" in live_signals:
        rate = float(live_signals["solana_slot_rate"])
        if rate >= 2.2:    s, n = 18, f"Solana slot 速率 {rate:.2f}/s，正常 (期望 ~2.5)"
        elif rate >= 1.8:  s, n = 35, f"Solana slot 速率 {rate:.2f}/s，轻度降速"
        elif rate >= 1.5:  s, n = 55, f"Solana slot 速率 {rate:.2f}/s，明显降速，清算可能延迟"
        else:              s, n = 90, f"Solana slot 速率 {rate:.2f}/s，严重降速 (期望 2.5/s)"
        dims["chain"] = s
        dim_sources["chain"] = "live"
        dim_notes_override["chain"] = n
    elif "vault_share_price_dropped" in live_signals and live_signals["vault_share_price_dropped"]:
        # Handled in market dim below
        pass

    # --- market dim: vault share price drop / concentration ---
    if live_signals.get("vault_share_price_dropped"):
        drop_pct = float(live_signals.get("vault_share_price_drop_pct", 0))
        if market_score is None or 100 > market_score:
            dims["market"] = 100
            dim_sources["market"] = "live"
            dim_notes_override["market"] = f"Vault Share Price 下跌 {drop_pct:.4f}%，疑似坏账"

    if "depositor_top1_share" in live_signals:
        share = float(live_signals["depositor_top1_share"])
        if share < 0.30:    s, n = 5,  f"Top1 存款人占比 {share*100:.1f}%，分散健康"
        elif share < 0.50:  s, n = 20, f"Top1 存款人占比 {share*100:.1f}%，集中度中等"
        elif share < 0.70:  s, n = 45, f"Top1 存款人占比 {share*100:.1f}%，挤兑风险升高"
        else:               s, n = 75, f"Top1 存款人占比 {share*100:.1f}%，单笔提取可致流动性危机"
        if market_score is None or s > market_score:
            dims["market"] = s
            dim_sources["market"] = "live"
            dim_notes_override["market"] = n

    if "stress_loss_ratio_20" in live_signals:
        ratio = float(live_signals["stress_loss_ratio_20"])
        if ratio < 0.001:    s, n = 5,   f"抵押 -20% 情景下损失 {ratio*100:.4f}%，韧性强"
        elif ratio < 0.005:  s, n = 20,  f"抵押 -20% 情景下损失 {ratio*100:.3f}%，可控"
        elif ratio < 0.01:   s, n = 40,  f"抵押 -20% 情景下损失 {ratio*100:.2f}%，关注"
        elif ratio < 0.03:   s, n = 65,  f"抵押 -20% 情景下损失 {ratio*100:.2f}%，警戒"
        else:                s, n = 100, f"抵押 -20% 情景下损失 {ratio*100:.1f}%，极度脆弱"
        if market_score is None or s > market_score:
            dims["market"] = s
            dim_sources["market"] = "live"
            dim_notes_override["market"] = n

    # --- governance dim: high-risk events / inactivity ---
    if live_signals.get("governance_change_recent"):
        dims["governance"] = max(80, dims.get("governance", 25))
        dim_sources["governance"] = "live"
        dim_notes_override["governance"] = "近 7 天发生 owner/curator/timelock 高危变更"
    elif "curator_inactive_days" in live_signals:
        days = float(live_signals["curator_inactive_days"])
        if days > 30:
            dims["governance"] = max(60, dims.get("governance", 25))
            dim_sources["governance"] = "live"
            dim_notes_override["governance"] = f"Curator 已 {days:.0f} 天未操作，疑似失活"
        elif days > 14:
            dims["governance"] = max(40, dims.get("governance", 25))
            dim_sources["governance"] = "live"
            dim_notes_override["governance"] = f"Curator 已 {days:.0f} 天未操作，建议关注"

    # --- yield dim: APY premium vs peer median ---
    if "apy_premium_pct" in live_signals:
        s, n = _apy_premium_to_score(max(0, float(live_signals["apy_premium_pct"])))
        dims["yield"] = s
        dim_sources["yield"] = "live"
        dim_notes_override["yield"] = n

    key = (protocol, chain.lower(), asset.upper())
    has_live = any(s == "live" for s in dim_sources.values())
    baseline_dims = get_dim_scores(protocol, chain, asset)
    if key in PRODUCT_TOTAL:
        # Use authoritative baseline + delta from live signals
        total = float(PRODUCT_TOTAL[key])
        if has_live:
            for k, _, w in DIMENSIONS:
                if dim_sources[k] == "live":
                    delta = dims[k] - baseline_dims.get(k, 25)
                    total += delta * w
            total = round(total, 1)
            total = max(0, min(100, total))
    else:
        # No authoritative baseline — pure weighted sum
        total = 0.0
        for k, _, w in DIMENSIONS:
            total += dims.get(k, 25) * w
        total = round(total, 1)

    dim_details = {}
    for k, label, w in DIMENSIONS:
        score = dims.get(k, 25)
        notes = dim_notes_override.get(k) or DIM_NOTES.get((protocol, k), "")
        dim_details[k] = {"score": score, "weight": w, "label": label,
                           "notes": notes, "source": dim_sources[k]}

    apy = apy or 0.0
    adj_lin = apy * (1 - total / 100)
    adj_exp = apy * math.exp(-2 * total / 100)

    return RiskResult(
        total=total, level=_level(total), dimensions=dim_details,
        adjusted_yield_linear=round(adj_lin, 3),
        adjusted_yield_exp=round(adj_exp, 3),
        raw_apy=apy, veto_flags=[],
        live_signals=live_signals,
    )


# ---------- Veto rules (§7) ----------

def check_veto_rules(
    *, stablecoin_price: float | None = None,
    bad_debt_ratio: float | None = None,
    share_price_drop: bool = False,
    oracle_deviation: float | None = None,
    oracle_stale_seconds: int | None = None,
    oracle_heartbeat_seconds: int = 86400,
    utilization: float | None = None,
    withdraw_10_failed: bool = False,
    sequencer_down: bool = False,
    sequencer_down_seconds: int = 0,
) -> list[str]:
    """Return list of veto messages; non-empty = hard fail (level forced to E)."""
    flags = []
    if stablecoin_price is not None and stablecoin_price < 0.98:
        flags.append(f"稳定币价格 ${stablecoin_price:.4f} < $0.98")
    if bad_debt_ratio is not None and bad_debt_ratio > 0.002:
        flags.append(f"坏账率 {bad_debt_ratio*100:.2f}% > 0.2%")
    if share_price_drop:
        flags.append("Vault Share Price 下降")
    if oracle_deviation is not None and oracle_deviation > 0.03:
        flags.append(f"Oracle 偏差 {oracle_deviation*100:.2f}% > 3%")
    # Heartbeat-aware: only flag if age > heartbeat × 1.5
    if oracle_stale_seconds is not None and oracle_stale_seconds > oracle_heartbeat_seconds * 1.5:
        flags.append(f"Oracle 已停滞 {oracle_stale_seconds/3600:.1f}h (心跳 {oracle_heartbeat_seconds/3600:.0f}h)")
    if utilization is not None and utilization > 0.97:
        flags.append(f"利用率 {utilization*100:.1f}% > 97%")
    if withdraw_10_failed:
        flags.append("10% 提现模拟失败")
    if sequencer_down and sequencer_down_seconds > 600:
        flags.append(f"L2 Sequencer 已停机 {sequencer_down_seconds/60:.0f} 分钟")
    return flags
