AAVE_V3_POOL_ABI = [
    {"inputs": [{"name": "user", "type": "address"}], "name": "getUserAccountData",
     "outputs": [{"name": "totalCollateralBase", "type": "uint256"}, {"name": "totalDebtBase", "type": "uint256"},
         {"name": "availableBorrowsBase", "type": "uint256"}, {"name": "currentLiquidationThreshold", "type": "uint256"},
         {"name": "ltv", "type": "uint256"}, {"name": "healthFactor", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]
AAVE_V3_POOL_BASE = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
