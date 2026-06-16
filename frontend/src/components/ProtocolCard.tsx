type ChainBreakdown = {
  chain: string;
  chain_full: string;
  tvl_usd: number;
  apy: number;
  pools: number;
  by_asset?: Record<string, { tvl_usd: number; apy: number; pools: number }>;
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

export function ProtocolCard({ protocol: p, onToggle, onDelete }: Props) {
  const hasChains = p.chains_breakdown && p.chains_breakdown.length > 0;
  const links = getLinks(p);

  return (
    <div className={`bg-gray-900 rounded-lg p-4 border ${p.enabled ? 'border-gray-700' : 'border-gray-800 opacity-60'}`}>
      <div className="flex justify-between items-start">
        <div className="flex-1">
          <h3 className="font-semibold">{p.name}</h3>
          <div className="flex gap-2 mt-1 flex-wrap items-center">
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
        </div>
        <div className="flex gap-2">
          <button onClick={() => onToggle(p.id)}
            className={`text-xs px-3 py-1 rounded ${p.enabled ? 'bg-green-800 text-green-200' : 'bg-gray-700 text-gray-400'}`}>
            {p.enabled ? '已启用' : '已禁用'}
          </button>
          <button onClick={() => onDelete(p.id)} className="text-xs text-red-400 hover:text-red-300">删除</button>
        </div>
      </div>

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
