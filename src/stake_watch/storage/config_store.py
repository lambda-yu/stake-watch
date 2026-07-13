from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from stake_watch.config import AppSettings, IntervalConfig, RiskConfig, WalletConfig
from stake_watch.storage.tables import AppSettingsRow, ProtocolConfigRow, RpcEndpointRow, WalletRow, CexVenueRow
from stake_watch.models.cex import CexVenue

class ConfigStore:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def add_wallet(self, chain: str, address: str, label: str | None = None) -> WalletRow:
        async with self._sf() as s:
            row = WalletRow(chain=chain, address=address, label=label, created_at=datetime.now(timezone.utc))
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return row

    async def list_wallets(self) -> list[WalletRow]:
        async with self._sf() as s:
            result = await s.execute(select(WalletRow))
            return list(result.scalars().all())

    async def delete_wallet(self, wallet_id: int):
        async with self._sf() as s:
            row = await s.get(WalletRow, wallet_id)
            if row:
                await s.delete(row)
                await s.commit()

    async def upsert_rpc(self, chain: str, primary_url: str, fallback_urls: list[str]):
        async with self._sf() as s:
            result = await s.execute(select(RpcEndpointRow).where(RpcEndpointRow.chain == chain))
            row = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row:
                row.primary_url = primary_url
                row.fallback_urls = json.dumps(fallback_urls)
                row.updated_at = now
            else:
                row = RpcEndpointRow(chain=chain, primary_url=primary_url,
                    fallback_urls=json.dumps(fallback_urls), updated_at=now)
                s.add(row)
            await s.commit()

    async def get_rpc(self, chain: str) -> RpcEndpointRow | None:
        async with self._sf() as s:
            result = await s.execute(select(RpcEndpointRow).where(RpcEndpointRow.chain == chain))
            return result.scalar_one_or_none()

    async def list_rpc(self) -> list[RpcEndpointRow]:
        async with self._sf() as s:
            result = await s.execute(select(RpcEndpointRow))
            return list(result.scalars().all())

    async def add_protocol(self, name: str, chain: str, collector: str, enabled: bool = True,
                           safety_rank: int | None = None, safety_score: float | None = None,
                           reference_apy: str | None = None, primary_risks: list[str] | None = None,
                           vault_address: str | None = None, defillama_slug: str | None = None,
                           pool_filter: str | None = None,
                           protocol_type: str | None = None) -> ProtocolConfigRow:
        async with self._sf() as s:
            now = datetime.now(timezone.utc)
            row = ProtocolConfigRow(name=name, chain=chain, collector=collector, enabled=enabled,
                safety_rank=safety_rank, safety_score=safety_score, reference_apy=reference_apy,
                primary_risks=json.dumps(primary_risks or []),
                vault_address=vault_address, defillama_slug=defillama_slug,
                pool_filter=pool_filter, protocol_type=protocol_type,
                created_at=now, updated_at=now)
            s.add(row)
            await s.commit()
            await s.refresh(row)
            return row

    async def list_protocols(self) -> list[ProtocolConfigRow]:
        async with self._sf() as s:
            result = await s.execute(select(ProtocolConfigRow))
            return list(result.scalars().all())

    async def get_protocol(self, protocol_id: int) -> ProtocolConfigRow | None:
        async with self._sf() as s:
            return await s.get(ProtocolConfigRow, protocol_id)

    async def toggle_protocol(self, protocol_id: int):
        async with self._sf() as s:
            row = await s.get(ProtocolConfigRow, protocol_id)
            if row:
                row.enabled = not row.enabled
                row.updated_at = datetime.now(timezone.utc)
                await s.commit()

    async def update_protocol(self, protocol_id: int, **fields):
        async with self._sf() as s:
            row = await s.get(ProtocolConfigRow, protocol_id)
            if not row:
                return None
            for k, v in fields.items():
                if hasattr(row, k) and v is not None:
                    setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
            await s.commit()
            await s.refresh(row)
            return row

    async def delete_protocol(self, protocol_id: int):
        async with self._sf() as s:
            row = await s.get(ProtocolConfigRow, protocol_id)
            if row:
                await s.delete(row)
                await s.commit()

    async def set_setting(self, key: str, value):
        async with self._sf() as s:
            result = await s.execute(select(AppSettingsRow).where(AppSettingsRow.key == key))
            row = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row:
                row.value = json.dumps(value)
                row.updated_at = now
            else:
                row = AppSettingsRow(key=key, value=json.dumps(value), updated_at=now)
                s.add(row)
            await s.commit()

    async def get_setting(self, key: str):
        async with self._sf() as s:
            result = await s.execute(select(AppSettingsRow).where(AppSettingsRow.key == key))
            row = result.scalar_one_or_none()
            return json.loads(row.value) if row else None

    async def import_seed_if_empty(self, seed_path: str = "config/seed.yaml"):
        """Import seed.yaml into DB. Protocol-family seed only runs on an empty
        protocol table; CEX venues are gated independently so upgrades from
        pre-CEX installs still seed venue defaults.

        Returns True if any seed branch actually inserted rows, False otherwise.
        """
        import yaml
        from pathlib import Path

        path = Path(seed_path)
        if not path.exists():
            return False

        data = yaml.safe_load(path.read_text()) or {}
        seeded_any = False

        # Protocol family (RPC/intervals/risk/protocols/wallets) — only on empty DB
        existing = await self.list_protocols()
        if not existing:
            seeded_any = True
            # Import RPC endpoints
            for chain, rpc_data in data.get("rpc", {}).items():
                primary = rpc_data if isinstance(rpc_data, str) else rpc_data.get("primary", "")
                fallback = [] if isinstance(rpc_data, str) else rpc_data.get("fallback", [])
                await self.upsert_rpc(chain, primary, fallback)

            # Import intervals
            for key, value in data.get("intervals", {}).items():
                await self.set_setting(f"intervals.{key}", value)

            # Import risk thresholds
            for key, value in data.get("risk", {}).items():
                await self.set_setting(f"risk.{key}", value)

            # Import protocols
            for proto in data.get("protocols", []):
                await self.add_protocol(
                    name=proto["name"], chain=proto["chain"], collector=proto["collector"],
                    enabled=proto.get("enabled", True),
                    safety_rank=proto.get("safety_rank"),
                    safety_score=proto.get("safety_score"),
                    reference_apy=proto.get("reference_apy"),
                    primary_risks=proto.get("primary_risks", []),
                    vault_address=proto.get("vault_address"),
                    defillama_slug=proto.get("defillama_slug"),
                    pool_filter=proto.get("pool_filter"),
                    protocol_type=proto.get("protocol_type"))

            # Import wallets
            for wallet in data.get("wallets", []):
                if wallet.get("address"):
                    await self.add_wallet(wallet["chain"], wallet["address"], wallet.get("label"))

        # CEX venues — independently gated so upgrades still seed
        existing_cex = await self.list_cex_venues()
        if not existing_cex and data.get("cex_venues"):
            seeded_any = True
            for entry in data.get("cex_venues", []):
                await self.upsert_cex_venue(CexVenue(**entry))

        return seeded_any

    async def upsert_cex_venue(self, venue: CexVenue) -> CexVenueRow:
        async with self._sf() as s:
            now = datetime.now(timezone.utc)
            row = await s.get(CexVenueRow, venue.name)
            if row:
                row.display_name = venue.display_name
                row.enabled = venue.enabled
                row.assets_json = json.dumps(venue.assets)
                row.notes = venue.notes
                row.updated_at = now
            else:
                row = CexVenueRow(
                    name=venue.name, display_name=venue.display_name,
                    enabled=venue.enabled,
                    assets_json=json.dumps(venue.assets),
                    notes=venue.notes,
                    created_at=now, updated_at=now,
                )
                s.add(row)
            await s.commit()
            await s.refresh(row)
            return row

    async def list_cex_venues(self) -> list[CexVenueRow]:
        async with self._sf() as s:
            result = await s.execute(select(CexVenueRow).order_by(CexVenueRow.name))
            return list(result.scalars().all())

    async def list_enabled_cex_venues(self) -> list[CexVenueRow]:
        async with self._sf() as s:
            result = await s.execute(
                select(CexVenueRow).where(CexVenueRow.enabled == True)  # noqa: E712
                                  .order_by(CexVenueRow.name))
            return list(result.scalars().all())

    async def patch_cex_venue(self, name: str, *, enabled: bool | None = None,
                              assets: list[str] | None = None,
                              notes: str | None = None) -> CexVenueRow | None:
        async with self._sf() as s:
            row = await s.get(CexVenueRow, name)
            if not row:
                return None
            if enabled is not None:
                row.enabled = enabled
            if assets is not None:
                row.assets_json = json.dumps(assets)
            if notes is not None:
                row.notes = notes
            row.updated_at = datetime.now(timezone.utc)
            await s.commit()
            await s.refresh(row)
            return row

    async def list_protocol_entries(self) -> list:
        """Return protocols as ProtocolEntry objects for collector building."""
        import json
        from stake_watch.config import ProtocolEntry
        rows = await self.list_protocols()
        return [ProtocolEntry(
            name=r.name, chain=r.chain, collector=r.collector, enabled=r.enabled,
            safety_rank=r.safety_rank, safety_score=r.safety_score,
            reference_apy=r.reference_apy,
            primary_risks=json.loads(r.primary_risks) if r.primary_risks else [],
            vault_address=r.vault_address, defillama_slug=r.defillama_slug,
            pool_filter=getattr(r, "pool_filter", None),
        ) for r in rows]

    async def load_app_settings(self) -> AppSettings:
        async with self._sf() as s:
            result = await s.execute(select(AppSettingsRow))
            rows = {r.key: json.loads(r.value) for r in result.scalars().all()}
        wallets_rows = await self.list_wallets()
        return AppSettings(
            wallets=[WalletConfig(chain=w.chain, address=w.address) for w in wallets_rows],
            intervals=IntervalConfig(
                positions=rows.get("intervals.positions", 300),
                protocol_stats=rows.get("intervals.protocol_stats", 900),
                stablecoin_price=rows.get("intervals.stablecoin_price", 60),
                stablecoin_supply=rows.get("intervals.stablecoin_supply", 600),
                reserves=rows.get("intervals.reserves", 21600)),
            risk=RiskConfig(
                liquidation_warning=rows.get("risk.liquidation_warning", 1.3),
                liquidation_critical=rows.get("risk.liquidation_critical", 1.1),
                depeg_warning=rows.get("risk.depeg_warning", 0.005),
                depeg_critical=rows.get("risk.depeg_critical", 0.02),
                tvl_crash_threshold=rows.get("risk.tvl_crash_threshold", 0.15),
                apy_change_threshold=rows.get("risk.apy_change_threshold", 0.30)))
