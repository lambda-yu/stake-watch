from enum import Enum

class Chain(str, Enum):
    SOLANA = "solana"
    ETHEREUM = "ethereum"
    BSC = "bsc"
    BASE = "base"

class PositionType(str, Enum):
    SUPPLY = "supply"
    BORROW = "borrow"
    STAKE = "stake"
    LP = "lp"
    VAULT = "vault"
