"""Curated multi-dimensional risk evaluation per protocol.

Each protocol gets a score (0-10) and a Chinese explanation per dimension:
  - contract: smart contract maturity / audit history
  - governance: how decentralised/upgradeable is control
  - liquidity: depth + ability to withdraw
  - oracle: price feed reliability
  - collateral: quality of accepted collateral / borrowers
"""
from __future__ import annotations

EVALUATIONS: dict[str, dict[str, dict]] = {
    "aave_v3_base": {
        "contract":   {"score": 9, "notes": "Aave V3 历史审计 10+ 次（OpenZeppelin/Trail of Bits/Certora 形式化），主网运行 2 年+ 无重大漏洞"},
        "governance": {"score": 8, "notes": "Aave DAO 链上治理 + Guardian 多签紧急暂停。参数调整通过 ARFC + AIP 流程"},
        "liquidity":  {"score": 8, "notes": "Base USDC 池约 $176M，未触及 supply cap，提款无延迟"},
        "oracle":     {"score": 8, "notes": "Chainlink 喂价 + sequencer uptime feed + 偏离断路器"},
        "collateral": {"score": 8, "notes": "抵押品限蓝筹 (cbETH/WETH/wstETH/cbBTC/tBTC)，LTV/Liquidation 阈值保守"},
    },
    "sky_susds": {
        "contract":   {"score": 9, "notes": "Sky (前 MakerDAO) 运行 8+ 年，核心 DSS 系统经过 10+ 次审计"},
        "governance": {"score": 7, "notes": "Sky 治理 + Endgame SubDAO 结构，存在治理攻击向量但有 GSM delay"},
        "liquidity":  {"score": 9, "notes": "sUSDS 实时按 SSR 累计，可即时 redeem 为 USDS；USDS 总供应 $9B+"},
        "oracle":     {"score": 9, "notes": "SSR 由治理设定，不依赖外部价格预言机；USDS:USDC PSM 1:1"},
        "collateral": {"score": 7, "notes": "RWA 敞口 ~50%（包括美债/链上信贷），有合规和 RWA 流动性风险"},
    },
    "morpho_steakhouse_usdc": {
        "contract":   {"score": 8, "notes": "Morpho Blue 核心合约不可升级，Steakhouse Vault 是 ERC-4626 + curator 模式"},
        "governance": {"score": 7, "notes": "Steakhouse Financial 作为 curator 决定市场分配，存在 curator 风险"},
        "liquidity":  {"score": 7, "notes": "Base 池约 $X, 大额提款可能需等待 Morpho 市场再平衡"},
        "oracle":     {"score": 7, "notes": "依赖 Morpho 各底层市场的 Chainlink/Pyth 喂价"},
        "collateral": {"score": 8, "notes": "Steakhouse 偏保守，多为蓝筹 ETH LST 和 RWA 高评级敞口"},
    },
    "morpho_gauntlet_usdc_prime": {
        "contract":   {"score": 8, "notes": "Morpho Blue 不可升级；Gauntlet 是知名风控团队"},
        "governance": {"score": 7, "notes": "Gauntlet 作为 curator 调整 supply cap 和市场分配"},
        "liquidity":  {"score": 7, "notes": "Prime vault 流动性较好，但仍受底层 Morpho 市场利用率限制"},
        "oracle":     {"score": 7, "notes": "依赖底层市场喂价，Gauntlet 会主动监控"},
        "collateral": {"score": 8, "notes": "Prime 等级抵押品质量要求高，主要为 wstETH/cbBTC/WETH 等"},
    },
    "compound_v3_usdc": {
        "contract":   {"score": 9, "notes": "Compound 2018 起运行，V3 (Comet) 设计单基础资产架构，审计完善"},
        "governance": {"score": 7, "notes": "COMP 治理，Timelock + Guardian 紧急暂停"},
        "liquidity":  {"score": 8, "notes": "Base USDC ~$8.6M，Ethereum ~$326M，提款流畅"},
        "oracle":     {"score": 8, "notes": "Chainlink + 价格偏离保护，集成 sequencer uptime feed"},
        "collateral": {"score": 8, "notes": "蓝筹抵押品，参数由 Gauntlet/OpenZeppelin 风控团队推荐"},
    },
    "fluid_usdc": {
        "contract":   {"score": 7, "notes": "Instadapp 团队，已审计但合约较新（2024 上线），复杂的 vault 协议"},
        "governance": {"score": 6, "notes": "由 Instadapp 团队/DAO 控制，去中心化程度中等"},
        "liquidity":  {"score": 7, "notes": "依赖 Smart Debt/Smart Col 机制，复杂的流动性层"},
        "oracle":     {"score": 7, "notes": "Chainlink 主导，部分用 DEX 中间价"},
        "collateral": {"score": 7, "notes": "支持 USDC/USDT/GHO/sUSDS/wstETH/ETH 等主流资产"},
    },
    "morpho_pangolins_usdc": {
        "contract":   {"score": 8, "notes": "Morpho Blue 核心不可升级；Pangolins 是较新的 curator"},
        "governance": {"score": 6, "notes": "Pangolins 团队规模较小，治理透明度有限"},
        "liquidity":  {"score": 6, "notes": "vault TVL 较小，大额进出可能滑点偏高"},
        "oracle":     {"score": 7, "notes": "底层 Morpho 市场喂价"},
        "collateral": {"score": 7, "notes": "策略偏激进，追求更高 APY，抵押品有一定风险"},
    },
    "morpho_gauntlet_rwa_usdc": {
        "contract":   {"score": 8, "notes": "Morpho Blue 不可升级，Gauntlet 风控成熟"},
        "governance": {"score": 7, "notes": "Gauntlet curator 模式同 Prime"},
        "liquidity":  {"score": 6, "notes": "RWA 抵押品流动性较差，大额提款可能受限"},
        "oracle":     {"score": 7, "notes": "Chainlink + RWA 估值数据源"},
        "collateral": {"score": 6, "notes": "接受 RWA 抵押品（美债/私人信贷），合规和流动性风险显著高于纯链上"},
    },
    "jupiter_lend": {
        "contract":   {"score": 7, "notes": "Jupiter Lend 2025 上线，OtterSec/Sec3 审计，时间较短"},
        "governance": {"score": 7, "notes": "Jupiter DAO + JUP 治理，已上线 governance"},
        "liquidity":  {"score": 7, "notes": "USDC 池 ~$402M，统一流动性层但有 withdrawal smoothing"},
        "oracle":     {"score": 7, "notes": "Pyth + Switchboard 双源，Solana 生态标准"},
        "collateral": {"score": 7, "notes": "支持 SOL/JLP/JitoSOL/cbBTC 等，参数相对保守"},
    },
    "kamino_usdc": {
        "contract":   {"score": 7, "notes": "Kamino 2023 起，K-Lend 2024 上线，OtterSec/Halborn 审计"},
        "governance": {"score": 7, "notes": "Kamino DAO + KMNO 治理"},
        "liquidity":  {"score": 7, "notes": "Main Market USDC ~$110M，4 月曾达 100% 利用率"},
        "oracle":     {"score": 7, "notes": "Pyth + Switchboard"},
        "collateral": {"score": 7, "notes": "支持 SOL LST/BTC/JLP/JUP 等，部分抵押品流动性中等"},
    },
}

DEFAULT_EVALUATION = {
    "contract":   {"score": 7, "notes": "暂无详细评估"},
    "governance": {"score": 7, "notes": "暂无详细评估"},
    "liquidity":  {"score": 7, "notes": "暂无详细评估"},
    "oracle":     {"score": 7, "notes": "暂无详细评估"},
    "collateral": {"score": 7, "notes": "暂无详细评估"},
}


def evaluate(name: str) -> dict[str, dict]:
    """Return the 5-dimension evaluation (score + notes) for a protocol."""
    return EVALUATIONS.get(name, DEFAULT_EVALUATION)
