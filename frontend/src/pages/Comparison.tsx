import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';

type Row = {
  protocol: string; protocol_type?: string;
  chain: string; chain_full: string; asset: string;
  apy: number; tvl_usd: number;
  utilization?: number | null;
  withdrawable_ratio?: number | null;
  supply_cap_usage?: number | null;
  borrow_cap_usage?: number | null;
  apy_inverted?: boolean;
  apy_premium_pct?: number | null;
  tvl_drop_7d?: number | null;
  borrow_apy?: number | null;
  risk_total: number; risk_level: 'A'|'B'|'C'|'D'|'E';
  adjusted_yield_linear: number; adjusted_yield_exp: number;
  liquidity_coeff: number; stable_safety_coeff: number;
  composite_score: number;
  has_live_signals?: boolean;
};

type SortKey = 'composite' | 'apy' | 'adjusted' | 'risk' | 'tvl';

const LEVEL_BADGE: Record<string, string> = {
  A: 'bg-green-900/60 text-green-300 border-green-700',
  B: 'bg-blue-900/60 text-blue-300 border-blue-700',
  C: 'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  D: 'bg-orange-900/60 text-orange-300 border-orange-700',
  E: 'bg-red-900/60 text-red-300 border-red-700',
};

function formatTvl(v: number): string {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export function Comparison() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendNote, setSendNote] = useState<string | null>(null);
  const [screenshotUrl, setScreenshotUrl] = useState<string>('http://localhost:5173');
  const [showScreenshotConfig, setShowScreenshotConfig] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('composite');
  const [filterAsset, setFilterAsset] = useState<string>('all');
  const [filterChain, setFilterChain] = useState<string>('all');
  const [filterLevel, setFilterLevel] = useState<string>('all');

  const reload = async () => {
    setLoading(true);
    try { setRows((await api.comparison.get()).rows); }
    catch { setRows([]); }
    finally { setLoading(false); }
  };

  const refresh = async () => {
    setRefreshing(true);
    setRefreshNote(null);
    try {
      const r = await api.protocols.refresh();
      const ok = r?.refreshed?.length ?? 0;
      const failed = r?.failed?.length ?? 0;
      setRefreshNote(`已拉取 ${ok} 个协议${failed ? `，${failed} 个失败` : ''}`);
      await reload();
    } catch (e: any) {
      setRefreshNote(`刷新失败: ${e.message}`);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    reload();
    api.comparison.screenshotConfig()
      .then(r => setScreenshotUrl(r.frontend_url))
      .catch(() => {});
  }, []);

  const sendTelegram = async () => {
    setSending(true);
    setSendNote(null);
    try {
      const r = await api.comparison.sendTelegram();
      if (r.success) {
        const kb = r.bytes ? ` (${(r.bytes / 1024).toFixed(0)}KB)` : '';
        setSendNote(`✓ 已推送${kb}`);
      } else {
        setSendNote(`✗ ${r.error || '推送失败'}`);
      }
    } catch (e: any) {
      setSendNote(`✗ ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  const saveScreenshotUrl = async (url: string) => {
    try {
      const r = await api.comparison.updateScreenshotConfig({ frontend_url: url });
      setScreenshotUrl(r.frontend_url);
    } catch (e: any) {
      setSendNote(`✗ 配置保存失败: ${e.message}`);
    }
  };

  const filtered = useMemo(() => {
    let r = rows;
    if (filterAsset !== 'all') r = r.filter(x => x.asset === filterAsset);
    if (filterChain !== 'all') r = r.filter(x => x.chain === filterChain);
    if (filterLevel !== 'all') r = r.filter(x => x.risk_level === filterLevel);
    const sorted = [...r];
    sorted.sort((a, b) => {
      switch (sortKey) {
        case 'apy':       return b.apy - a.apy;
        case 'adjusted':  return b.adjusted_yield_exp - a.adjusted_yield_exp;
        case 'risk':      return a.risk_total - b.risk_total;
        case 'tvl':       return b.tvl_usd - a.tvl_usd;
        default:          return b.composite_score - a.composite_score;
      }
    });
    return sorted;
  }, [rows, sortKey, filterAsset, filterChain, filterLevel]);

  const chains = useMemo(() => Array.from(new Set(rows.map(r => r.chain))), [rows]);
  const assets = useMemo(() => Array.from(new Set(rows.map(r => r.asset))), [rows]);

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h1 className="text-2xl font-bold">协议对比</h1>
          <p className="text-gray-500 text-sm mt-1">
            按 综合选择分 = 风险调整收益 × 流动性系数 × 稳定币安全系数 排序
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {refreshNote && (
            <span className="text-xs text-gray-400">{refreshNote}</span>
          )}
          {sendNote && (
            <span className={`text-xs ${sendNote.startsWith('✓') ? 'text-green-400' : 'text-red-400'}`}>
              {sendNote}
            </span>
          )}
          <button onClick={() => setShowScreenshotConfig(s => !s)}
            title="配置截图所用的前端 URL"
            className="text-gray-400 hover:text-gray-200 text-xs px-2 py-2">
            ⚙
          </button>
          <button onClick={sendTelegram} disabled={sending || loading || refreshing}
            title="截当前页面发送到 Telegram"
            className="bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-700 text-white px-4 py-2 rounded text-sm">
            {sending ? '推送中... (~10s)' : '📷 推送到 Telegram'}
          </button>
          <button onClick={reload} disabled={loading || refreshing}
            className="bg-gray-800 hover:bg-gray-700 disabled:bg-gray-900 text-gray-200 border border-gray-700 px-3 py-2 rounded text-sm">
            {loading ? '加载中...' : '重新加载'}
          </button>
          <button onClick={refresh} disabled={loading || refreshing}
            title="拉取最新链上 APY/TVL 后重新计算"
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white px-4 py-2 rounded text-sm">
            {refreshing ? '拉取中... (~30s)' : '🔄 刷新数据'}
          </button>
        </div>
      </div>

      {showScreenshotConfig && (
        <div className="bg-gray-900 border border-gray-800 rounded p-3 mb-4 text-sm">
          <div className="flex items-center gap-2 flex-wrap">
            <label className="text-gray-400 whitespace-nowrap">截图前端 URL</label>
            <input
              value={screenshotUrl}
              onChange={e => setScreenshotUrl(e.target.value)}
              onBlur={() => saveScreenshotUrl(screenshotUrl)}
              placeholder="http://localhost:5173"
              className="flex-1 min-w-[300px] bg-gray-800 border border-gray-700 rounded px-2 py-1 font-mono text-xs"
            />
            <span className="text-xs text-gray-500">
              指向运行中的 Vite dev / 静态站点根；服务端 headless Chromium 会访问此 URL + /comparison
            </span>
          </div>
        </div>
      )}

      <div className="bg-gray-900 rounded-lg p-3 mb-4 flex gap-3 flex-wrap text-sm items-center">
        <div className="flex items-center gap-2">
          <label className="text-gray-400">排序</label>
          <select value={sortKey} onChange={e => setSortKey(e.target.value as SortKey)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1">
            <option value="composite">综合选择分</option>
            <option value="adjusted">风险调整收益</option>
            <option value="apy">原始 APY</option>
            <option value="risk">风险分（低到高）</option>
            <option value="tvl">TVL</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-gray-400">资产</label>
          <select value={filterAsset} onChange={e => setFilterAsset(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1">
            <option value="all">全部</option>
            {assets.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-gray-400">链</label>
          <select value={filterChain} onChange={e => setFilterChain(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1">
            <option value="all">全部</option>
            {chains.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-gray-400">等级</label>
          <select value={filterLevel} onChange={e => setFilterLevel(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1">
            <option value="all">全部</option>
            {['A','B','C','D','E'].map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <span className="text-gray-500 ml-auto">{filtered.length} / {rows.length} 个产品</span>
      </div>

      <div className="bg-gray-900 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800 text-gray-400 text-xs">
            <tr>
              <th className="text-left px-3 py-2">产品</th>
              <th className="text-left px-3 py-2">链 / 资产</th>
              <th className="text-right px-3 py-2">APY</th>
              <th className="text-right px-3 py-2">TVL</th>
              <th className="text-right px-3 py-2">利用率</th>
              <th className="text-right px-3 py-2">可提现</th>
              <th className="text-right px-3 py-2">Cap 使用</th>
              <th className="text-right px-3 py-2">同类Δ</th>
              <th className="text-center px-3 py-2">风险</th>
              <th className="text-right px-3 py-2">调整后</th>
              <th className="text-right px-3 py-2">综合分</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => {
              const utilColor = r.utilization == null
                ? 'text-gray-600'
                : r.utilization < 0.75 ? 'text-green-400'
                : r.utilization < 0.85 ? 'text-yellow-400'
                : r.utilization < 0.92 ? 'text-orange-400'
                : 'text-red-400';
              const wColor = r.withdrawable_ratio == null
                ? 'text-gray-600'
                : r.withdrawable_ratio > 0.30 ? 'text-green-400'
                : r.withdrawable_ratio > 0.15 ? 'text-yellow-400'
                : r.withdrawable_ratio > 0.05 ? 'text-orange-400'
                : 'text-red-400';
              const capMax = Math.max(r.supply_cap_usage || 0, r.borrow_cap_usage || 0);
              const capColor = capMax === 0 ? 'text-gray-600'
                : capMax < 0.8 ? 'text-green-400'
                : capMax < 0.92 ? 'text-yellow-400'
                : capMax < 0.98 ? 'text-orange-400'
                : 'text-red-400';
              const premColor = r.apy_premium_pct == null ? 'text-gray-600'
                : r.apy_premium_pct < 0.5 ? 'text-gray-400'
                : r.apy_premium_pct < 1.5 ? 'text-yellow-400'
                : r.apy_premium_pct < 3 ? 'text-orange-400'
                : 'text-red-400';
              return (
              <tr key={`${r.protocol}-${r.chain}-${r.asset}`}
                className={`border-t border-gray-800 ${i < 3 ? 'bg-gray-800/30' : ''}`}>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    {i < 3 && <span className="text-yellow-400 font-bold">#{i+1}</span>}
                    <span className="text-gray-200">{r.protocol}</span>
                    {r.has_live_signals && (
                      <span className="text-[10px] px-1 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-700">LIVE</span>
                    )}
                    {r.apy_inverted && (
                      <span className="text-[10px] px-1 py-0.5 rounded bg-red-900/60 text-red-300 border border-red-700" title="Supply ≥ Borrow APY">INV</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2 text-gray-400">{r.chain} · <span className="text-gray-300">{r.asset}</span></td>
                <td className="px-3 py-2 text-right font-mono text-blue-300">{r.apy.toFixed(2)}%</td>
                <td className="px-3 py-2 text-right font-mono text-gray-400">{formatTvl(r.tvl_usd)}</td>
                <td className={`px-3 py-2 text-right font-mono ${utilColor}`}>
                  {r.utilization != null ? `${(r.utilization*100).toFixed(0)}%` : '—'}
                </td>
                <td className={`px-3 py-2 text-right font-mono ${wColor}`}>
                  {r.withdrawable_ratio != null ? `${(r.withdrawable_ratio*100).toFixed(0)}%` : '—'}
                </td>
                <td className={`px-3 py-2 text-right font-mono ${capColor}`} title={
                  r.supply_cap_usage || r.borrow_cap_usage
                    ? `Supply ${((r.supply_cap_usage||0)*100).toFixed(0)}% / Borrow ${((r.borrow_cap_usage||0)*100).toFixed(0)}%`
                    : ''
                }>
                  {capMax > 0 ? `${(capMax*100).toFixed(0)}%` : '—'}
                </td>
                <td className={`px-3 py-2 text-right font-mono ${premColor}`}>
                  {r.apy_premium_pct != null ? `${r.apy_premium_pct >= 0 ? '+' : ''}${r.apy_premium_pct.toFixed(2)}` : '—'}
                </td>
                <td className="px-3 py-2 text-center">
                  <span className={`text-xs px-1.5 py-0.5 rounded border ${LEVEL_BADGE[r.risk_level]}`}>
                    {r.risk_level} · {r.risk_total.toFixed(0)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-green-300">{r.adjusted_yield_exp.toFixed(2)}%</td>
                <td className="px-3 py-2 text-right font-mono font-bold text-emerald-300">{r.composite_score.toFixed(3)}</td>
              </tr>
            );})}
            {filtered.length === 0 && (
              <tr><td colSpan={11} className="text-center py-8 text-gray-500">
                {rows.length === 0 ? '暂无数据 — 请先在"质押协议"页点击刷新 APY+TVL' : '无符合过滤条件的产品'}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 text-xs text-gray-500 leading-relaxed">
        <p><strong className="text-gray-400">综合分</strong>：风险调整收益（指数模型 <code>APY×e^(-2R/100)</code>）× 流动性系数（基于 TVL）× 稳定币系数（1 - 资产风险 / 100）</p>
        <p className="mt-1"><strong className="text-gray-400">前三名</strong>在风险可接受的前提下提供最优 risk-adjusted 收益，可作为核心配置参考。</p>
        <p className="mt-1"><strong className="text-gray-400">流动性系数</strong>：TVL ≥ $1B → 1.00；$300M-$1B → 0.95；$100M-$300M → 0.90；$30M-$100M → 0.80；$10M-$30M → 0.65；&lt;$10M → 0.45</p>
      </div>
    </div>
  );
}
