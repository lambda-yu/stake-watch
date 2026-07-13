from __future__ import annotations
from stake_watch.collectors.cex.base import CexEarnCollector
from stake_watch.models.cex import CexVenue


def build_cex_collector(venue: CexVenue) -> CexEarnCollector | None:
    match venue.name:
        case "binance":
            from stake_watch.collectors.cex.binance import BinanceEarnCollector
            return BinanceEarnCollector(venue.assets)
        case "okx":
            from stake_watch.collectors.cex.okx import OkxEarnCollector
            return OkxEarnCollector(venue.assets)
        case "bybit":
            from stake_watch.collectors.cex.bybit import BybitEarnCollector
            return BybitEarnCollector(venue.assets)
        case "gate":
            from stake_watch.collectors.cex.gate import GateEarnCollector
            return GateEarnCollector(venue.assets)
        case "bitget":
            from stake_watch.collectors.cex.bitget import BitgetEarnCollector
            return BitgetEarnCollector(venue.assets)
        case _:
            return None