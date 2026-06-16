type ChainBreakdown = {
  chain: string;
  chain_full: string;
  tvl_usd: number;
  apy: number;
  pools: number;
};

type Protocol = {
  id: number; name: string; chain: string; collector: string;
  enabled: boolean; safety_score: number | null; reference_apy: string | null;
  primary_risks: string[];
  live_tvl_usd?: number | null;
  live_apy?: number | null;
  live_pool_asset?: string | null;
  stats_updated_at?: string | null;
  chains_breakdown?: ChainBreakdown[] | null;
};
type Props = { protocol: Protocol; onToggle: (id: number) => void; onDelete: (id: number) => void };

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

export function ProtocolCard({ protocol: p, onToggle, onDelete }: Props) {
  const hasLive = p.live_tvl_usd != null || p.live_apy != null;
  const hasMultiChain = p.chains_breakdown && p.chains_breakdown.length > 1;

  return (
    <div className={`bg-gray-900 rounded-lg p-4 border ${p.enabled ? 'border-gray-700' : 'border-gray-800 opacity-60'}`}>
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <h3 className="font-semibold">{p.name}</h3>
          <div className="flex gap-2 mt-1 flex-wrap">
            <span className="text-xs bg-gray-700 px-2 py-0.5 rounded">{p.chain}</span>
            {p.safety_score && <span className="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded">安全 {p.safety_score}/10</span>}
            {p.reference_apy && <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded">参考 {p.reference_apy}</span>}
          </div>
          {p.primary_risks.length > 0 && (
            <div className="mt-2 text-xs text-gray-500">{p.primary_risks.join(' / ')}</div>
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

      {hasLive && (
        <div className="mt-3 pt-3 border-t border-gray-800 flex items-center gap-6 text-sm">
          {p.live_apy != null && (
            <div className="flex items-baseline gap-1">
              <span className="text-gray-500 text-xs">APY</span>
              <span className={`font-mono text-base ${p.live_apy > 5 ? 'text-green-400' : 'text-gray-200'}`}>
                {p.live_apy.toFixed(2)}%
              </span>
            </div>
          )}
          {p.live_tvl_usd != null && (
            <div className="flex items-baseline gap-1">
              <span className="text-gray-500 text-xs">质押量</span>
              <span className="font-mono text-base text-gray-200">{formatTvl(p.live_tvl_usd)}</span>
            </div>
          )}
          {p.live_pool_asset && (
            <div className="flex items-baseline gap-1">
              <span className="text-gray-500 text-xs">资产</span>
              <span className="text-xs">{p.live_pool_asset}</span>
            </div>
          )}
          {p.stats_updated_at && (
            <div className="ml-auto text-xs text-gray-600">
              {new Date(p.stats_updated_at).toLocaleString('zh-CN', { hour12: false })}
            </div>
          )}
        </div>
      )}

      {hasMultiChain && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <div className="text-xs text-gray-500 mb-2">多链部署 ({p.chains_breakdown!.length} 条链)</div>
          <div className="grid grid-cols-2 gap-2">
            {p.chains_breakdown!.map(c => (
              <div key={c.chain_full} className="bg-gray-800/50 rounded px-3 py-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded font-semibold ${CHAIN_COLORS[c.chain] || 'bg-gray-700 text-gray-300'}`}>
                    {c.chain}
                  </span>
                </div>
                <div className="flex gap-3 text-xs">
                  <span className={`font-mono ${c.apy > 5 ? 'text-green-400' : 'text-gray-300'}`}>
                    {c.apy.toFixed(2)}%
                  </span>
                  <span className="font-mono text-gray-400">{formatTvl(c.tvl_usd)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
