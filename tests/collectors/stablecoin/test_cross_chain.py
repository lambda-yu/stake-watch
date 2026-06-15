from stake_watch.collectors.stablecoin.cross_chain import CrossChainVerifier, STABLECOIN_WHITELIST

def test_known_usdc_ethereum():
    v = CrossChainVerifier()
    r = v.verify("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "USDC", "ethereum")
    assert r.is_verified is True
    assert r.token_type == "native"

def test_known_usdc_base():
    v = CrossChainVerifier()
    r = v.verify("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "USDC", "base")
    assert r.is_verified is True

def test_bridged_usdbc():
    v = CrossChainVerifier()
    r = v.verify("0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "USDC", "base")
    assert r.is_verified is True
    assert r.token_type == "bridged"
    assert r.risk_premium > 0

def test_unknown_address():
    v = CrossChainVerifier()
    r = v.verify("0x1234567890abcdef1234567890abcdef12345678", "USDC", "ethereum")
    assert r.is_verified is False

def test_solana_usdc():
    v = CrossChainVerifier()
    r = v.verify("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "USDC", "solana")
    assert r.is_verified is True
