"""Runtime risk-control evaluator for each protocol.

Evaluates the live state of a protocol against a small set of operational checks
(data freshness, TVL size, APY sanity, underlying stablecoin peg, etc.) and
returns a score (0-10) plus per-check details for display.

Score: start at 10, -1 per warning, -3 per critical, floored at 0.
"""
from __future__ import annotations

from datetime import datetime, timezone

from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage


def _fmt_tvl(v: float) -> str:
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.0f}K"
    return f"${v:.0f}"


def _check(key: str, label: str, status: str, value: str, detail: str) -> dict:
    return {"key": key, "label": label, "status": status, "value": value, "detail": detail}


async def evaluate_protocol_status(protocol_name: str, storage: Storage,
                                    config_store: ConfigStore) -> dict | None:
    protos = await config_store.list_protocols()
    p = next((x for x in protos if x.name == protocol_name), None)
    if not p:
        return None

    stats = await storage.get_latest_protocol_stats(protocol_name)
    checks: list[dict] = []

    # 1. 协议启用
    if not p.enabled:
        checks.append(_check("enabled", "协议启用状态", "critical",
            "已禁用", "协议已被手动关闭，不再采集与告警，存量持仓需人工跟踪"))
    else:
        checks.append(_check("enabled", "协议启用状态", "ok",
            "已启用", "调度器会按配置周期持续采集 APY / TVL / 持仓数据"))

    # 2. 数据新鲜度
    if stats and stats.updated_at:
        updated_at = stats.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - updated_at).total_seconds() / 60
        if age_min <= 30:
            checks.append(_check("freshness", "数据新鲜度", "ok",
                f"{age_min:.0f} 分钟前",
                f"最近 {age_min:.0f} 分钟内有更新，API/链上数据有效"))
        elif age_min <= 360:
            checks.append(_check("freshness", "数据新鲜度", "warning",
                f"{age_min:.0f} 分钟前",
                f"已 {age_min:.0f} 分钟未刷新，可能调度间隔过长或上游 API 异常"))
        else:
            checks.append(_check("freshness", "数据新鲜度", "critical",
                f"{age_min/60:.1f} 小时前",
                f"已 {age_min/60:.1f} 小时未更新，请检查官方 API 与 DefiLlama 状态"))
    else:
        checks.append(_check("freshness", "数据新鲜度", "critical",
            "无数据", "尚未采集到任何协议统计，请点击\"刷新 APY+TVL\""))

    # 3. TVL 规模
    if stats and stats.tvl_usd:
        tvl = float(stats.tvl_usd)
        if tvl >= 50_000_000:
            checks.append(_check("tvl", "TVL 规模", "ok", _fmt_tvl(tvl),
                "深度充足，大额进出价格冲击小，提款流动性有保障"))
        elif tvl >= 5_000_000:
            checks.append(_check("tvl", "TVL 规模", "warning", _fmt_tvl(tvl),
                "规模中等，大额操作可能产生滑点或撞 supply cap，建议分批"))
        else:
            checks.append(_check("tvl", "TVL 规模", "critical", _fmt_tvl(tvl),
                "TVL 偏小，提款流动性脆弱，单笔大额赎回可能受限"))
    else:
        checks.append(_check("tvl", "TVL 规模", "warning", "未知",
            "未取得 TVL 数据，无法评估流动性厚度"))

    # 4. APY 合理性
    if stats and stats.pools:
        primary = next((pp for pp in stats.pools if "USDC" in pp.asset.upper()), stats.pools[0])
        apy = primary.supply_apy or 0
        if 0 < apy <= 12:
            checks.append(_check("apy", "APY 合理区间", "ok", f"{apy:.2f}%",
                "APY 处于稳定币正常收益区间 (0-12%)，无明显异常激励"))
        elif 12 < apy <= 25:
            checks.append(_check("apy", "APY 合理区间", "warning", f"{apy:.2f}%",
                "APY 偏高 (12-25%)，可能来自临时激励或高利用率，关注可持续性"))
        elif apy > 25:
            checks.append(_check("apy", "APY 合理区间", "critical", f"{apy:.2f}%",
                "APY 异常高 (>25%)，多半是补贴或风险信号，谨慎追入"))
        else:
            checks.append(_check("apy", "APY 合理区间", "warning", f"{apy:.2f}%",
                "APY 为 0 或负值，需确认采集是否正确"))

    # 5. 底层稳定币 depeg
    if stats and stats.pools:
        try:
            snapshots = await storage.get_latest_stablecoin_snapshots()
        except Exception:
            snapshots = []
        token_priorities = ["USDC", "USDT", "USDS", "USD0", "USD1"]
        for token in token_priorities:
            if not any(token in p.asset.upper() for p in stats.pools):
                continue
            snap = next((s for s in snapshots if getattr(s, "token", "").upper() == token), None)
            if snap and getattr(snap, "median_price", None):
                price = float(snap.median_price)
                deviation = abs(price - 1)
                if deviation < 0.005:
                    checks.append(_check(f"peg_{token}", f"{token} 锚定", "ok",
                        f"${price:.4f}",
                        f"底层 {token} 价格偏离 < 0.5%，无 depeg 风险"))
                elif deviation < 0.02:
                    checks.append(_check(f"peg_{token}", f"{token} 锚定", "warning",
                        f"${price:.4f}",
                        f"{token} 偏离 {deviation*100:.2f}%，已触发 depeg warning 阈值"))
                else:
                    checks.append(_check(f"peg_{token}", f"{token} 锚定", "critical",
                        f"${price:.4f}",
                        f"{token} 偏离 {deviation*100:.2f}%，达 depeg critical，考虑减仓"))
                break  # only report one primary stable

    # 6. 链分布 (>1 chain = better resilience)
    chains_setting = await config_store.get_setting(f"protocols.{protocol_name}.chains")
    if chains_setting and isinstance(chains_setting, list):
        n = len(chains_setting)
        if n >= 2:
            chain_names = ", ".join(c.get("chain", "?") for c in chains_setting)
            checks.append(_check("chains", "多链分布", "ok", f"{n} 条链",
                f"协议在 {chain_names} 部署，跨链可分散单链风险"))
        else:
            chain_name = chains_setting[0].get("chain", "?") if chains_setting else "?"
            checks.append(_check("chains", "多链分布", "warning", "单链",
                f"仅在 {chain_name} 部署，承担该链共识/桥风险"))

    # Scoring
    score = 10.0
    for c in checks:
        if c["status"] == "warning":
            score -= 1
        elif c["status"] == "critical":
            score -= 3
    score = max(0.0, score)

    has_critical = any(c["status"] == "critical" for c in checks)
    has_warning = any(c["status"] == "warning" for c in checks)
    level = "critical" if has_critical else ("warning" if has_warning else "ok")

    # Risk Model v2 — adjusted yield + curated risk total
    try:
        from stake_watch.risk.risk_model import evaluate, check_veto_rules
        from stake_watch.risk.onchain_signals import (
            fetch_chainlink_price, fetch_sequencer_status, fetch_solana_health,
            fetch_pyth_price,
            CHAINLINK_FEEDS, SEQUENCER_FEEDS
        )
        from stake_watch.api.routes.protocols import PRIMARY_PRODUCT  # type: ignore
        primary_chain, primary_asset = PRIMARY_PRODUCT.get(protocol_name, (p.chain, "USDC"))
        apy = 0.0
        if stats and stats.pools:
            primary_pool = next((pp for pp in stats.pools if primary_asset in pp.asset.upper()),
                                 stats.pools[0])
            apy = float(primary_pool.supply_apy or 0)

        live_signals: dict = {}

        # ---- Chainlink price feed staleness + deviation ----
        rpc_list = await config_store.list_rpc()
        chain_rpc = next((r.primary_url for r in rpc_list if r.chain == primary_chain), None)
        if chain_rpc and (primary_chain, primary_asset) in CHAINLINK_FEEDS:
            cl = await fetch_chainlink_price(chain_rpc, primary_chain, primary_asset)
            if cl:
                live_signals["oracle_staleness_seconds"] = cl["age_seconds"]
                live_signals["oracle_heartbeat_seconds"] = cl["heartbeat_seconds"]
                deviation = abs(cl["price"] - 1.0)
                live_signals["oracle_deviation"] = deviation
                age_min = cl["age_seconds"] // 60
                hb_h = cl["heartbeat_seconds"] // 3600
                if cl["is_stale"]:
                    checks.append(_check("oracle_freshness", "Oracle 喂价新鲜度", "critical",
                        f"{age_min} 分钟",
                        f"Chainlink {primary_asset} 喂价已超心跳 {hb_h}h，可能停滞"))
                elif cl["age_seconds"] > cl["heartbeat_seconds"]:
                    checks.append(_check("oracle_freshness", "Oracle 喂价新鲜度", "warning",
                        f"{age_min} 分钟",
                        f"已接近心跳上限（{hb_h}h），关注"))
                else:
                    checks.append(_check("oracle_freshness", "Oracle 喂价新鲜度", "ok",
                        f"{age_min} 分钟",
                        f"喂价正常（心跳 {hb_h}h）, 当前价 ${cl['price']:.4f}"))

        # ---- Base Sequencer status ----
        if primary_chain in SEQUENCER_FEEDS:
            base_rpc = next((r.primary_url for r in rpc_list if r.chain == "base"), None)
            if base_rpc:
                seq = await fetch_sequencer_status(base_rpc, "base")
                if seq:
                    if not seq["is_up"]:
                        live_signals["sequencer_down"] = True
                        live_signals["sequencer_down_seconds"] = seq["seconds_in_status"]
                        checks.append(_check("sequencer", "Base Sequencer", "critical",
                            "已停机", f"已停机 {seq['seconds_in_status']//60} 分钟，所有 L2 交易暂停"))
                    elif seq["seconds_in_status"] < 3600:
                        live_signals["sequencer_recent_recovery"] = True
                        checks.append(_check("sequencer", "Base Sequencer", "warning",
                            "刚恢复", f"已运行 {seq['seconds_in_status']//60} 分钟，宽限期内谨慎"))
                    else:
                        days = seq["seconds_in_status"] // 86400
                        checks.append(_check("sequencer", "Base Sequencer", "ok",
                            "运行中", f"已稳定运行 {days} 天"))

        # ---- Solana network health (slot rate + TPS) ----
        if primary_chain == "solana":
            sol_rpc = next((r.primary_url for r in rpc_list if r.chain == "solana"), None)
            if sol_rpc:
                sol = await fetch_solana_health(sol_rpc)
                if sol:
                    live_signals["solana_slot_rate"] = sol["slot_rate"]
                    rate = sol["slot_rate"]
                    tps = sol["tps_non_vote"]
                    if sol["critical"]:
                        status = "critical"
                        detail = f"slot 速率 {rate:.2f}/s 严重偏低 (期望 2.5/s)，清算可能延迟"
                    elif sol["degraded"]:
                        status = "warning"
                        detail = f"slot 速率 {rate:.2f}/s 轻度降速，TPS {tps:.0f}"
                    else:
                        status = "ok"
                        detail = f"slot 速率 {rate:.2f}/s 正常，TPS {tps:.0f}"
                    checks.append(_check("solana_health", "Solana 网络健康", status,
                        f"{rate:.2f} slot/s", detail))

            # ---- Pyth price feed freshness (Solana protocols) ----
            pyth = await fetch_pyth_price([primary_asset])
            if pyth and primary_asset in pyth:
                pp = pyth[primary_asset]
                age = pp["age_seconds"]
                price = pp["price"]
                # Pyth high-frequency feeds publish ~400ms; >60s = degraded
                if age < 30:
                    checks.append(_check("pyth_freshness", "Pyth 喂价新鲜度", "ok",
                        f"{age}秒前", f"Pyth {primary_asset} ${price:.4f}，{age}秒前更新（高频）"))
                elif age < 120:
                    live_signals["oracle_staleness_seconds"] = max(live_signals.get("oracle_staleness_seconds", 0), age)
                    live_signals["oracle_heartbeat_seconds"] = 60
                    checks.append(_check("pyth_freshness", "Pyth 喂价新鲜度", "warning",
                        f"{age}秒前", f"Pyth {primary_asset} {age}s 未更新，预期 <30s"))
                else:
                    live_signals["oracle_staleness_seconds"] = max(live_signals.get("oracle_staleness_seconds", 0), age)
                    live_signals["oracle_heartbeat_seconds"] = 60
                    checks.append(_check("pyth_freshness", "Pyth 喂价新鲜度", "critical",
                        f"{age}秒前", f"Pyth {primary_asset} 已 {age}s 未更新，Solana 协议清算可能失效"))
                # Track deviation too
                deviation = abs(price - 1.0)
                existing_dev = live_signals.get("oracle_deviation", 0)
                live_signals["oracle_deviation"] = max(existing_dev, deviation)

        # ---- Morpho vault share price 24h trend ----
        if getattr(p, "vault_address", None) and protocol_name.startswith("morpho_"):
            try:
                latest = await storage.get_latest_vault_share_price(p.vault_address)
                old = await storage.get_vault_share_price_n_hours_ago(p.vault_address, 24)
                if latest and old:
                    drop_pct = (old - latest) / old * 100
                    if drop_pct > 0.05:
                        live_signals["vault_share_price_dropped"] = True
                        live_signals["vault_share_price_drop_pct"] = drop_pct
                        status = "critical" if drop_pct > 0.5 else "warning"
                        checks.append(_check("vault_share_price", "Vault Share Price 24h", status,
                            f"-{drop_pct:.4f}%",
                            f"24h 前 ${old:.6f} → 现 ${latest:.6f}，疑似坏账或费用扣除"))
                    else:
                        checks.append(_check("vault_share_price", "Vault Share Price 24h", "ok",
                            f"{'+' if drop_pct <= 0 else '-'}{abs(drop_pct):.4f}%",
                            f"24h 前 ${old:.6f} → 现 ${latest:.6f}，未发现异常下跌"))
                elif latest:
                    checks.append(_check("vault_share_price", "Vault Share Price", "ok",
                        f"${latest:.6f}",
                        "已记录最新 share price，24h 后可比对趋势"))
            except Exception:
                pass

            # ---- Morpho curator activity ----
            try:
                from stake_watch.collectors.morpho.morpho_api import (
                    fetch_vault_admin_events, summarize_vault_activity,
                    fetch_vault_bad_debt, fetch_vault_top_holders,
                    fetch_vault_stress_test,
                )
                # Bad debt across underlying markets
                bd = await fetch_vault_bad_debt(p.vault_address, primary_chain)
                if bd:
                    ratio = bd["bad_debt_ratio"]
                    live_signals["bad_debt_ratio"] = ratio
                    if ratio < 0.0001:
                        checks.append(_check("bad_debt", "底层市场坏账", "ok",
                            f"${bd['bad_debt_usd']:,.0f}",
                            f"坏账率 {ratio*100:.4f}%（含累计 ${bd['realized_bad_debt_usd']:,.0f}），可忽略"))
                    elif ratio < 0.002:
                        checks.append(_check("bad_debt", "底层市场坏账", "warning",
                            f"${bd['bad_debt_usd']:,.0f}",
                            f"坏账率 {ratio*100:.3f}%，需关注"))
                    else:
                        checks.append(_check("bad_debt", "底层市场坏账", "critical",
                            f"${bd['bad_debt_usd']:,.0f}",
                            f"坏账率 {ratio*100:.3f}% > 0.2%，已触发否决"))

                # Top depositor concentration
                conc = await fetch_vault_top_holders(p.vault_address, primary_chain, n=10)
                if conc:
                    top1 = conc["top1_share"]
                    top5 = conc["top5_share"]
                    live_signals["depositor_top1_share"] = top1
                    live_signals["depositor_top5_share"] = top5
                    if top1 < 0.30:
                        checks.append(_check("concentration", "存款人集中度", "ok",
                            f"Top1 {top1*100:.0f}%",
                            f"Top1 {top1*100:.0f}% / Top5 {top5*100:.0f}%，{conc['total_holders']:,} 位持有人，分散良好"))
                    elif top1 < 0.50:
                        checks.append(_check("concentration", "存款人集中度", "warning",
                            f"Top1 {top1*100:.0f}%",
                            f"Top1 持有 {top1*100:.0f}% (${conc['holders'][0]['assets_usd']/1e6:.0f}M)，集中度中等"))
                    elif top1 < 0.70:
                        checks.append(_check("concentration", "存款人集中度", "warning",
                            f"Top1 {top1*100:.0f}%",
                            f"Top1 {top1*100:.0f}% / Top5 {top5*100:.0f}%，挤兑风险升高"))
                    else:
                        checks.append(_check("concentration", "存款人集中度", "critical",
                            f"Top1 {top1*100:.0f}%",
                            f"Top1 {top1*100:.0f}% (${conc['holders'][0]['assets_usd']/1e6:.0f}M)，单笔退出即可瘫痪流动性"))

                # Stress test (collateral price drops)
                stress = await fetch_vault_stress_test(p.vault_address, primary_chain)
                if stress:
                    scenarios = stress["scenarios"]
                    loss_20 = scenarios.get("drop_20", {}).get("vault_loss_ratio", 0)
                    loss_30 = scenarios.get("drop_30", {}).get("vault_loss_ratio", 0)
                    live_signals["stress_loss_ratio_20"] = loss_20
                    if loss_20 < 0.001:
                        checks.append(_check("stress_test", "压力测试 (抵押 -20%)", "ok",
                            f"{loss_20*100:.4f}%",
                            f"-20%/-30% 价跌情景下潜在损失 ${scenarios['drop_20']['vault_loss_usd']/1e6:.2f}M/${scenarios['drop_30']['vault_loss_usd']/1e6:.2f}M，覆盖充足"))
                    elif loss_20 < 0.005:
                        checks.append(_check("stress_test", "压力测试 (抵押 -20%)", "warning",
                            f"{loss_20*100:.3f}%",
                            f"-20% 情景下潜在损失 ${scenarios['drop_20']['vault_loss_usd']/1e6:.2f}M ({loss_20*100:.3f}% TVL)，建议关注抵押品风险"))
                    elif loss_20 < 0.01:
                        checks.append(_check("stress_test", "压力测试 (抵押 -20%)", "warning",
                            f"{loss_20*100:.2f}%",
                            f"-20% 情景下潜在损失 {loss_20*100:.2f}% TVL，进入警戒区"))
                    elif loss_20 < 0.03:
                        checks.append(_check("stress_test", "压力测试 (抵押 -20%)", "critical",
                            f"{loss_20*100:.2f}%",
                            f"-20% 情景下损失 {loss_20*100:.2f}% TVL（${scenarios['drop_20']['vault_loss_usd']/1e6:.1f}M），高度暴露"))
                    else:
                        checks.append(_check("stress_test", "压力测试 (抵押 -20%)", "critical",
                            f"{loss_20*100:.1f}%",
                            f"-20% 情景下损失 {loss_20*100:.1f}% TVL，极度脆弱"))

                events = await fetch_vault_admin_events(p.vault_address, primary_chain)
                if events:
                    summary = summarize_vault_activity(events)
                    high = summary["high_risk_recent"]
                    days = summary["days_since_last_action"]
                    if high:
                        types = ", ".join(e["type"] for e in high[:3])
                        checks.append(_check("curator_activity", "Curator/治理动作", "critical",
                            f"{len(high)} 次高危",
                            f"近 7 天发生高危治理事件: {types}（owner/curator/timelock 变更）"))
                        live_signals["governance_change_recent"] = True
                    elif days is None:
                        checks.append(_check("curator_activity", "Curator 活跃度", "warning",
                            "无记录", "未拉取到 curator 行为，建议核查"))
                    elif days < 1:
                        checks.append(_check("curator_activity", "Curator 活跃度", "ok",
                            f"{days*24:.0f}h 前",
                            f"最近动作 {summary['last_action_type']} ({days*24:.0f}h 前)，24h 内调仓 {summary['reallocate_24h']} 次"))
                    elif days < 14:
                        checks.append(_check("curator_activity", "Curator 活跃度", "ok",
                            f"{days:.1f}天 前",
                            f"最近动作 {summary['last_action_type']}，仍在正常调仓节奏"))
                    else:
                        checks.append(_check("curator_activity", "Curator 活跃度", "warning",
                            f"{days:.0f}天 前",
                            f"已 {days:.0f} 天未操作，curator 可能不活跃"))
                        # bump governance dim slightly
                        cur = dims_governance = None  # placeholder; signal carried by risk_model below
                        live_signals["curator_inactive_days"] = days
            except Exception:
                pass

        rm = evaluate(protocol_name, primary_chain, primary_asset, apy,
                       live_signals=live_signals or None)

        # ---- Withdrawal simulation check ----
        try:
            chains_breakdown = await config_store.get_setting(f"protocols.{protocol_name}.chains") or []
            for entry in chains_breakdown:
                by_asset = entry.get("by_asset") or {}
                info = by_asset.get(primary_asset)
                if info and info.get("withdrawable_ratio") is not None:
                    wr = float(info["withdrawable_ratio"])
                    if wr >= 1.0:
                        checks.append(_check("withdraw_sim", "提现模拟 10/50/100%", "ok",
                            "全通过", "100% 即时提现可行，流动性深度充足"))
                    elif wr >= 0.50:
                        checks.append(_check("withdraw_sim", "提现模拟 10/50/100%", "warning",
                            f"10%, 50% ok",
                            f"100% 提现需排队（可用 {wr*100:.0f}%）"))
                    elif wr >= 0.10:
                        checks.append(_check("withdraw_sim", "提现模拟 10/50/100%", "warning",
                            "仅 10% 通过",
                            f"50% 提现失败，仅 10% 可即时退出（可用 {wr*100:.1f}%）"))
                    else:
                        checks.append(_check("withdraw_sim", "提现模拟 10/50/100%", "critical",
                            "全部失败",
                            f"10% 提现都不可行（可用 {wr*100:.1f}%），已触发否决"))
                    # Compound coverage ratio → bad debt proxy
                    if info.get("collateral_coverage") is not None:
                        cov = float(info["collateral_coverage"])
                        if cov > 0:
                            if cov >= 1.5:
                                checks.append(_check("coverage", "抵押覆盖率", "ok",
                                    f"{cov:.2f}x",
                                    f"抵押品价值 / 借款 {cov:.2f}x，无结构性坏账"))
                            elif cov >= 1.1:
                                checks.append(_check("coverage", "抵押覆盖率", "warning",
                                    f"{cov:.2f}x",
                                    f"覆盖率偏低 {cov:.2f}x，关注抵押品价格波动"))
                            else:
                                checks.append(_check("coverage", "抵押覆盖率", "critical",
                                    f"{cov:.2f}x",
                                    f"覆盖率 {cov:.2f}x，疑似结构性坏账"))
                            if info.get("bad_debt_ratio"):
                                live_signals["bad_debt_ratio"] = max(
                                    live_signals.get("bad_debt_ratio", 0),
                                    float(info["bad_debt_ratio"]))
                    break
        except Exception:
            pass

        # Veto: stablecoin depeg from latest snapshot
        veto_kwargs = {}
        try:
            snaps = await storage.get_latest_stablecoin_snapshots()
            snap = next((s for s in snaps if getattr(s, "token", "").upper() == primary_asset), None)
            if snap and getattr(snap, "median_price", None):
                veto_kwargs["stablecoin_price"] = float(snap.median_price)
        except Exception:
            pass
        if "oracle_staleness_seconds" in live_signals:
            veto_kwargs["oracle_stale_seconds"] = live_signals["oracle_staleness_seconds"]
            veto_kwargs["oracle_heartbeat_seconds"] = live_signals.get("oracle_heartbeat_seconds", 86400)
        if "oracle_deviation" in live_signals:
            veto_kwargs["oracle_deviation"] = live_signals["oracle_deviation"]
        if live_signals.get("sequencer_down"):
            veto_kwargs["sequencer_down"] = True
            veto_kwargs["sequencer_down_seconds"] = live_signals.get("sequencer_down_seconds", 0)
        if live_signals.get("vault_share_price_dropped"):
            veto_kwargs["share_price_drop"] = True
        veto_flags = check_veto_rules(**veto_kwargs)

        risk_model_block = {
            "total": rm.total, "level": rm.level,
            "primary_chain": primary_chain, "primary_asset": primary_asset,
            "apy": apy,
            "adjusted_yield_linear": rm.adjusted_yield_linear,
            "adjusted_yield_exp": rm.adjusted_yield_exp,
            "dimensions": [
                {"key": k, "label": v["label"], "weight": v["weight"],
                 "score": v["score"], "notes": v["notes"], "source": v.get("source", "curated")}
                for k, v in rm.dimensions.items()
            ],
            "veto_flags": veto_flags,
            "live_signals": live_signals,
        }
    except Exception as e:
        risk_model_block = {"error": str(e)}

    return {
        "score": round(score, 1),
        "level": level,
        "checks": checks,
        "risk_model": risk_model_block,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
