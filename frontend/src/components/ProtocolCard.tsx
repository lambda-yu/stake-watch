type ChainBreakdown = {
  chain: string;
  chain_full: string;
  tvl_usd: number;
  apy: number;
  pools: number;
  by_asset?: Record<string, { tvl_usd: number; apy: number; pools: number }>;
};

type RiskDim = { key: string; label: string; weight: number; score: number; notes: string; source?: 'curated' | 'live' };

type Protocol = {
  id: number; name: string; chain: string; collector: string;
  enabled: boolean; safety_score: number | null; reference_apy: string | null;
  primary_risks: string[];
  protocol_type?: string | null;
  primary_chain?: string | null;
  primary_asset?: string | null;
  risk_total?: number | null;
  risk_level?: 'A' | 'B' | 'C' | 'D' | 'E' | null;
  risk_dimensions?: RiskDim[] | null;
  risk_evaluated_at?: string | null;
  live_tvl_usd?: number | null;
  live_apy?: number | null;
  live_pool_asset?: string | null;
  stats_updated_at?: string | null;
  chains_breakdown?: ChainBreakdown[] | null;
  usdc_apy?: number | null;
  usdc_tvl?: number | null;
  usdt_apy?: number | null;
  usdt_tvl?: number | null;
  primary_asset?: string | null;
  primary_asset_apy?: number | null;
  primary_asset_tvl?: number | null;
  defillama_slug?: string | null;
  vault_address?: string | null;
};
type Props = { protocol: Protocol; onToggle: (id: number) => void; onDelete: (id: number) => void; onReevaluate?: (id: number) => void };

import { useEffect, useState } from 'react';
import { RiskRadar } from './RiskRadar';
import { api } from '../api/client';

type RiskCheck = { key: string; label: string; status: 'ok' | 'warning' | 'critical'; value: string; detail: string };
type RiskModelBlock = {
  total: number; level: 'A'|'B'|'C'|'D'|'E';
  primary_chain: string; primary_asset: string;
  apy: number;
  adjusted_yield_linear: number;
  adjusted_yield_exp: number;
  dimensions: RiskDim[];
  veto_flags: string[];
};
type RiskStatus = { score: number; level: 'ok' | 'warning' | 'critical'; checks: RiskCheck[]; risk_model?: RiskModelBlock; updated_at: string | null };

const STATUS_DOT: Record<string, string> = {
  ok: 'bg-green-500',
  warning: 'bg-yellow-500',
  critical: 'bg-red-500',
};
const STATUS_TEXT: Record<string, string> = {
  ok: 'text-green-400',
  warning: 'text-yellow-400',
  critical: 'text-red-400',
};
const LEVEL_BADGE: Record<string, string> = {
  A: 'bg-green-900/60 text-green-300 border-green-700',
  B: 'bg-blue-900/60 text-blue-300 border-blue-700',
  C: 'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  D: 'bg-orange-900/60 text-orange-300 border-orange-700',
  E: 'bg-red-900/60 text-red-300 border-red-700',
};
const LEVEL_DESC: Record<string, string> = {
  A: '低风险 · 核心配置', B: '较稳健 · 正常配置', C: '中等 · 控制仓位',
  D: '高风险 · 小比例', E: '极高 · 不建议',
};

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diffSec = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (diffSec < 60) return `${Math.floor(diffSec)}秒前`;
  if (diffSec < 3600) return `${Math.floor(diffSec/60)}分钟前`;
  if (diffSec < 86400) return `${Math.floor(diffSec/3600)}小时前`;
  return d.toLocaleString('zh-CN', { hour12: false });
}

const DIM_LABELS: { key: string; label: string }[] = [
  { key: 'contract',   label: '合约' },
  { key: 'governance', label: '治理' },
  { key: 'liquidity',  label: '流动性' },
  { key: 'oracle',     label: '预言机' },
  { key: 'collateral', label: '抵押品' },
];

function formatTvl(v: number): string {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

const CHAIN_COLORS: Record<string, string> = {
  ETH: 'bg-blue-900/50 text-blue-300',
  BASE: 'bg-blue-800/50 text-blue-200',
  SOL: 'bg-purple-900/50 text-purple-300',
  BSC: 'bg-yellow-900/50 text-yellow-300',
};

const TYPE_TAGS: Record<string, { label: string; cls: string }> = {
  lending: { label: '借贷', cls: 'bg-cyan-900/50 text-cyan-300' },
  vault:   { label: '金库', cls: 'bg-pink-900/50 text-pink-300' },
  savings: { label: '储蓄', cls: 'bg-amber-900/50 text-amber-300' },
};

const PROTOCOL_LINKS: Record<string, { home: string; app?: string; defillama?: string }> = {
  aave_v3_base: { home: 'https://aave.com', app: 'https://app.aave.com', defillama: 'https://defillama.com/protocol/aave-v3' },
  compound_v3_usdc: { home: 'https://compound.finance', app: 'https://app.compound.finance', defillama: 'https://defillama.com/protocol/compound-v3' },
  sky_susds: { home: 'https://sky.money', app: 'https://app.sky.money', defillama: 'https://defillama.com/protocol/sky-lending' },
  fluid_usdc: { home: 'https://fluid.io', app: 'https://fluid.io', defillama: 'https://defillama.com/protocol/fluid-lending' },
  jupiter_lend: { home: 'https://jup.ag', app: 'https://jup.ag/lend', defillama: 'https://defillama.com/protocol/jupiter-lend' },
  kamino_usdc: { home: 'https://kamino.finance', app: 'https://app.kamino.finance', defillama: 'https://defillama.com/protocol/kamino-lend' },
  morpho_steakhouse_usdc: { home: 'https://morpho.org', app: 'https://app.morpho.org/base/vault/0xBEEFE94c8aD530842bfE7d8B397938fFc1cb83b2', defillama: 'https://defillama.com/protocol/morpho-blue' },
  morpho_gauntlet_usdc_prime: { home: 'https://morpho.org', app: 'https://app.morpho.org/base/vault/0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61', defillama: 'https://defillama.com/protocol/morpho-blue' },
  morpho_pangolins_usdc: { home: 'https://morpho.org', app: 'https://app.morpho.org/base/vault/0x1401d1271C47648AC70cBcdfA3776D4A87CE006B', defillama: 'https://defillama.com/protocol/morpho-blue' },
  morpho_gauntlet_rwa_usdc: { home: 'https://morpho.org', app: 'https://app.morpho.org/ethereum/vault/0xA8875aaeBc4f830524e35d57F9772FfAcbdD6C45', defillama: 'https://defillama.com/protocol/morpho-blue' },
};

function getLinks(p: Protocol) {
  const links = PROTOCOL_LINKS[p.name];
  if (links) return links;
  if (p.defillama_slug) {
    return { home: '', defillama: `https://defillama.com/protocol/${p.defillama_slug}` };
  }
  return null;
}

export function ProtocolCard({ protocol: p, onToggle, onDelete, onReevaluate }: Props) {
  const hasChains = p.chains_breakdown && p.chains_breakdown.length > 0;
  const links = getLinks(p);
  const [showRadar, setShowRadar] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [showRiskCtrl, setShowRiskCtrl] = useState(false);
  const [refreshingCtrl, setRefreshingCtrl] = useState(false);

  const loadRiskStatus = async (force = false) => {
    setRefreshingCtrl(true);
    try { setRiskStatus(await api.protocols.riskStatus(p.id, force)); }
    catch { /* ignore */ }
    finally { setRefreshingCtrl(false); }
  };
  useEffect(() => { loadRiskStatus(); }, [p.id]);

  return (
    <div className={`bg-gray-900 rounded-lg p-4 border ${p.enabled ? 'border-gray-700' : 'border-gray-800 opacity-60'}`}>
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <h3 className="font-semibold">{p.name}</h3>
          <div className="flex gap-2 mt-1 flex-wrap items-center">
            {p.protocol_type && TYPE_TAGS[p.protocol_type] && (
              <span className={`text-xs px-2 py-0.5 rounded ${TYPE_TAGS[p.protocol_type].cls}`}>
                {TYPE_TAGS[p.protocol_type].label}
              </span>
            )}
            {p.safety_score && <span className="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded">安全 {p.safety_score}/10</span>}
            {p.reference_apy && <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded">参考 {p.reference_apy}</span>}
            {links && (
              <div className="flex gap-1 ml-1">
                {links.app && (
                  <a href={links.app} target="_blank" rel="noopener" title="协议应用"
                    className="text-xs px-2 py-0.5 rounded bg-blue-900/40 text-blue-300 hover:bg-blue-900/70 inline-flex items-center gap-1">
                    🔗 App
                  </a>
                )}
                {links.home && (
                  <a href={links.home} target="_blank" rel="noopener" title="协议主页"
                    className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300 hover:bg-gray-600">
                    主页
                  </a>
                )}
                {links.defillama && (
                  <a href={links.defillama} target="_blank" rel="noopener" title="DefiLlama"
                    className="text-xs px-2 py-0.5 rounded bg-purple-900/40 text-purple-300 hover:bg-purple-900/70">
                    🦙
                  </a>
                )}
              </div>
            )}
          </div>
          {p.primary_risks.length > 0 && (
            <div className="mt-2 text-xs text-gray-500">{p.primary_risks.join(' / ')}</div>
          )}
          {p.risk_total !== undefined && p.risk_total !== null && p.risk_level && (
            <button onClick={() => setShowRadar(s => !s)}
              className="mt-2 text-xs text-indigo-300 hover:text-indigo-200 inline-flex items-center gap-2">
              <span>{showRadar ? '▼' : '▶'}</span>
              <span>风险评估</span>
              <span className={`px-1.5 py-0.5 rounded border ${LEVEL_BADGE[p.risk_level]}`}>
                {p.risk_level} · {p.risk_total.toFixed(0)}
              </span>
              <span className="text-gray-500">{LEVEL_DESC[p.risk_level]}</span>
            </button>
          )}
          {riskStatus && (
            <button onClick={() => setShowRiskCtrl(s => !s)}
              className="mt-2 ml-3 text-xs text-emerald-300 hover:text-emerald-200 inline-flex items-center gap-1">
              <span>{showRiskCtrl ? '▼' : '▶'}</span>
              <span>🛡️ 风控状态</span>
              <span className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[riskStatus.level]}`}></span>
              <span className="text-gray-500">{riskStatus.score.toFixed(1)}/10</span>
              {riskStatus.risk_model && (
                <span className="text-gray-500 ml-1">
                  调整后 {riskStatus.risk_model.adjusted_yield_linear.toFixed(2)}%
                </span>
              )}
            </button>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={() => onToggle(p.id)}
            className={`text-xs px-3 py-1 rounded ${p.enabled ? 'bg-green-800 text-green-200' : 'bg-gray-700 text-gray-400'}`}>
            {p.enabled ? '已启用' : '已禁用'}
          </button>
          <button onClick={() => onDelete(p.id)} className="text-xs text-red-400 hover:text-red-300">删除</button>
        </div>
      </div>

      {showRadar && p.risk_dimensions && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <div className="flex justify-between items-center mb-2">
            <div className="text-xs text-gray-500">
              风险评估明细 · {p.primary_chain?.toUpperCase()} {p.primary_asset} ·{' '}
              <span className={`px-1.5 py-0.5 rounded border ${LEVEL_BADGE[p.risk_level || 'C']}`}>
                {p.risk_level} · {p.risk_total?.toFixed(0)}/100
              </span>
              {p.risk_evaluated_at && (
                <span className="ml-2 text-gray-600">· 更新 {fmtTime(p.risk_evaluated_at)}</span>
              )}
            </div>
            {onReevaluate && (
              <button
                onClick={async () => {
                  setEvaluating(true);
                  try {
                    await onReevaluate(p.id);
                    await loadRiskStatus(false);  // refresh in-card risk status too
                  } finally { setEvaluating(false); }
                }}
                disabled={evaluating}
                className="text-xs px-2 py-0.5 rounded bg-indigo-900/50 text-indigo-300 hover:bg-indigo-900/70 disabled:opacity-50"
              >
                {evaluating ? '刷新中...' : '🔄 刷新评估'}
              </button>
            )}
          </div>
          <div className="flex gap-4 items-start">
            <div className="shrink-0">
              <RiskRadar dimensions={p.risk_dimensions.map(d => ({ key: d.key, label: d.label, score: d.score }))} size={220} max={100} />
            </div>
            <div className="flex-1 space-y-1.5 text-xs">
              {p.risk_dimensions.map(d => {
                const color = d.score <= 20 ? 'text-green-400' : d.score <= 40 ? 'text-yellow-400' : d.score <= 55 ? 'text-orange-400' : 'text-red-400';
                return (
                  <div key={d.key} className="bg-gray-800/50 rounded px-2 py-1.5">
                    <div className="flex justify-between">
                      <span className="text-gray-300 font-medium">
                        {d.label}
                        <span className="text-gray-600 ml-1">({(d.weight*100).toFixed(0)}%)</span>
                        {d.source === 'live' && (
                          <span className="ml-1 text-[10px] px-1 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-700">LIVE</span>
                        )}
                      </span>
                      <span className={`font-mono ${color}`}>{d.score.toFixed(0)}/100</span>
                    </div>
                    {d.notes && <div className="text-gray-500 mt-0.5 leading-snug">{d.notes}</div>}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {showRiskCtrl && riskStatus && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <div className="flex justify-between items-center mb-2">
            <div className="text-xs text-gray-500">
              实时风控 ·{' '}
              <span className={STATUS_TEXT[riskStatus.level]}>
                {riskStatus.level === 'ok' ? '正常' : riskStatus.level === 'warning' ? '注意' : '严重'}
              </span>
              {' · '}评分 {riskStatus.score.toFixed(1)}/10
              {riskStatus.risk_model && (
                <>
                  {' · '}风险调整收益 {riskStatus.risk_model.adjusted_yield_linear.toFixed(2)}% (线性) / {riskStatus.risk_model.adjusted_yield_exp.toFixed(2)}% (指数)
                </>
              )}
              {riskStatus.updated_at && (
                <span className="ml-2 text-gray-600">· 更新 {fmtTime(riskStatus.updated_at)}</span>
              )}
            </div>
            <button onClick={() => loadRiskStatus(true)} disabled={refreshingCtrl}
              className="text-xs px-2 py-0.5 rounded bg-emerald-900/50 text-emerald-300 hover:bg-emerald-900/70 disabled:opacity-50">
              {refreshingCtrl ? '刷新中...' : '🔄 刷新风控'}
            </button>
          </div>
          {riskStatus.risk_model && riskStatus.risk_model.veto_flags.length > 0 && (
            <div className="mb-2 p-2 rounded border border-red-700 bg-red-900/30 text-xs text-red-300">
              <div className="font-semibold mb-1">⛔ 一票否决触发</div>
              {riskStatus.risk_model.veto_flags.map((f, i) => <div key={i}>· {f}</div>)}
            </div>
          )}
          <div className="space-y-1.5 text-xs">
            {riskStatus.checks.map(c => (
              <div key={c.key} className="bg-gray-800/50 rounded px-2 py-1.5">
                <div className="flex items-center gap-2 justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full ${STATUS_DOT[c.status]}`}></span>
                    <span className="text-gray-300 font-medium">{c.label}</span>
                  </div>
                  <span className={`font-mono ${STATUS_TEXT[c.status]}`}>{c.value}</span>
                </div>
                <div className="text-gray-500 mt-0.5 leading-snug pl-4">{c.detail}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {hasChains && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-500">
              链上数据 ({p.chains_breakdown!.length} {p.chains_breakdown!.length > 1 ? '条链' : '条链'})
            </span>
            {p.stats_updated_at && (
              <span className="text-xs text-gray-600">
                {new Date(p.stats_updated_at).toLocaleString('zh-CN', { hour12: false })}
              </span>
            )}
          </div>
          <div className="space-y-1.5">
            {p.chains_breakdown!.map(c => (
              <div key={c.chain_full} className="bg-gray-800/50 rounded px-3 py-2">
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-xs px-1.5 py-0.5 rounded font-semibold ${CHAIN_COLORS[c.chain] || 'bg-gray-700 text-gray-300'}`}>
                    {c.chain}
                  </span>
                  <span className="font-mono text-xs text-gray-400">{formatTvl(c.tvl_usd)}</span>
                </div>
                <div className="flex gap-4 text-xs">
                  {c.by_asset?.USDC && (
                    <span>
                      <span className="text-blue-400">USDC</span>{' '}
                      <span className={`font-mono ${c.by_asset.USDC.apy > 5 ? 'text-green-400' : 'text-gray-300'}`}>
                        {c.by_asset.USDC.apy.toFixed(2)}%
                      </span>{' '}
                      <span className="text-gray-500">{formatTvl(c.by_asset.USDC.tvl_usd)}</span>
                    </span>
                  )}
                  {c.by_asset?.USDT && (
                    <span>
                      <span className="text-green-400">USDT</span>{' '}
                      <span className={`font-mono ${c.by_asset.USDT.apy > 5 ? 'text-green-400' : 'text-gray-300'}`}>
                        {c.by_asset.USDT.apy.toFixed(2)}%
                      </span>{' '}
                      <span className="text-gray-500">{formatTvl(c.by_asset.USDT.tvl_usd)}</span>
                    </span>
                  )}
                  {c.by_asset?.USDS && (
                    <span>
                      <span className="text-orange-400">USDS</span>{' '}
                      <span className={`font-mono ${c.by_asset.USDS.apy > 5 ? 'text-green-400' : 'text-gray-300'}`}>
                        {c.by_asset.USDS.apy.toFixed(2)}%
                      </span>{' '}
                      <span className="text-gray-500">{formatTvl(c.by_asset.USDS.tvl_usd)}</span>
                    </span>
                  )}
                  {c.by_asset?.DAI && (
                    <span>
                      <span className="text-yellow-400">DAI</span>{' '}
                      <span className={`font-mono ${c.by_asset.DAI.apy > 5 ? 'text-green-400' : 'text-gray-300'}`}>
                        {c.by_asset.DAI.apy.toFixed(2)}%
                      </span>{' '}
                      <span className="text-gray-500">{formatTvl(c.by_asset.DAI.tvl_usd)}</span>
                    </span>
                  )}
                  {!c.by_asset?.USDC && !c.by_asset?.USDT && !c.by_asset?.USDS && !c.by_asset?.DAI && (
                    <span className={`font-mono ${c.apy > 5 ? 'text-green-400' : 'text-gray-300'}`}>
                      {c.apy.toFixed(2)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
