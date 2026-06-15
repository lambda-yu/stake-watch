MORPHO_BLUE_ABI = [
    {"inputs": [{"name": "id", "type": "bytes32"}], "name": "market",
     "outputs": [{"name": "totalSupplyAssets", "type": "uint128"}, {"name": "totalSupplyShares", "type": "uint128"},
         {"name": "totalBorrowAssets", "type": "uint128"}, {"name": "totalBorrowShares", "type": "uint128"},
         {"name": "lastUpdate", "type": "uint128"}, {"name": "fee", "type": "uint128"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "id", "type": "bytes32"}], "name": "idToMarketParams",
     "outputs": [{"name": "loanToken", "type": "address"}, {"name": "collateralToken", "type": "address"},
         {"name": "oracle", "type": "address"}, {"name": "irm", "type": "address"}, {"name": "lltv", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "id", "type": "bytes32"}, {"name": "user", "type": "address"}], "name": "position",
     "outputs": [{"name": "supplyShares", "type": "uint256"}, {"name": "borrowShares", "type": "uint128"},
         {"name": "collateral", "type": "uint128"}],
     "stateMutability": "view", "type": "function"},
]

METAMORPHO_VAULT_ABI = [
    {"inputs": [], "name": "totalAssets", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalSupply", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "assets", "type": "uint256"}], "name": "convertToShares", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "shares", "type": "uint256"}], "name": "convertToAssets", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "owner", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "curator", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "guardian", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "fee", "outputs": [{"type": "uint96"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "timelock", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "lastTotalAssets", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MORPHO", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "asset", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "id", "type": "bytes32"}], "name": "config",
     "outputs": [{"name": "cap", "type": "uint184"}, {"name": "enabled", "type": "bool"}, {"name": "removableAt", "type": "uint64"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "supplyQueueLength", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "index", "type": "uint256"}], "name": "supplyQueue", "outputs": [{"type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "withdrawQueueLength", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "index", "type": "uint256"}], "name": "withdrawQueue", "outputs": [{"type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "owner", "type": "address"}], "name": "maxWithdraw", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "owner", "type": "address"}], "name": "balanceOf", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]

ORACLE_ABI = [
    {"inputs": [], "name": "price", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]

MORPHO_BLUE_BASE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
