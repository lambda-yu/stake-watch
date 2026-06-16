import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { ProtocolCard } from '../components/ProtocolCard';

const CHAINS = ['base', 'ethereum', 'solana', 'bsc'];

const GROUPS: { key: string; label: string; match: (name: string) => boolean }[] = [
  { key: 'morpho', label: 'Morpho Vaults', match: n => n.startsWith('morpho_') },
  { key: 'aave', label: 'Aave', match: n => n.startsWith('aave_') },
  { key: 'compound', label: 'Compound', match: n => n.startsWith('compound_') },
  { key: 'sky', label: 'Sky / Maker', match: n => n.startsWith('sky_') || n.startsWith('maker_') },
  { key: 'fluid', label: 'Fluid', match: n => n.startsWith('fluid_') },
  { key: 'jupiter', label: 'Jupiter', match: n => n.startsWith('jupiter_') },
  { key: 'kamino', label: 'Kamino', match: n => n.startsWith('kamino_') },
];

function groupProtocols(protocols: any[]) {
  const groups: { key: string; label: string; protocols: any[] }[] = [];
  const unmatched: any[] = [];
  for (const g of GROUPS) {
    const matched = protocols.filter(p => g.match(p.name));
    if (matched.length > 0) groups.push({ key: g.key, label: g.label, protocols: matched });
  }
  for (const p of protocols) {
    if (!GROUPS.some(g => g.match(p.name))) unmatched.push(p);
  }
  if (unmatched.length > 0) groups.push({ key: 'other', label: '其他', protocols: unmatched });
  return groups;
}

export function Protocols() {
  const [protocols, setProtocols] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', chain: 'base', collector: 'defillama', defillama_slug: '', safety_score: '' });
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<any>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  const reload = async () => { try { setProtocols(await api.protocols.list()); } catch {} };
  useEffect(() => { reload(); }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.protocols.add({
      ...form, safety_score: form.safety_score ? Number(form.safety_score) : null, enabled: true,
    });
    setForm({ name: '', chain: 'base', collector: 'defillama', defillama_slug: '', safety_score: '' });
    setShowForm(false);
    reload();
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshResult(null);
    try {
      const r = await api.protocols.refresh();
      setRefreshResult(r);
      await reload();
    } catch (e: any) {
      setRefreshResult({ failed: [{ name: 'all', reason: e.message }] });
    } finally {
      setRefreshing(false);
    }
  };

  const groups = groupProtocols(protocols);

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h1 className="text-2xl font-bold">质押协议</h1>
          <p className="text-gray-500 text-sm mt-1">管理链上借贷和质押协议的监控配置</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleRefresh} disabled={refreshing}
            className="bg-green-600 hover:bg-green-700 disabled:bg-gray-700 text-white px-4 py-2 rounded text-sm">
            {refreshing ? '刷新中...' : '刷新 APY+TVL'}
          </button>
          <button onClick={() => setShowForm(!showForm)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm">
            {showForm ? '取消' : '添加协议'}
          </button>
        </div>
      </div>

      {refreshResult && (
        <div className="mb-4 bg-gray-900 rounded-lg p-3 text-xs">
          {refreshResult.refreshed?.length > 0 && (
            <div className="text-green-400 mb-1">
              ✓ 成功刷新 {refreshResult.refreshed.length} 个协议
            </div>
          )}
          {refreshResult.failed?.length > 0 && (
            <div className="text-red-400 space-y-0.5">
              {refreshResult.failed.map((f: any, i: number) => (
                <div key={i}>✗ {f.name}: {f.reason}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {showForm && (
        <form onSubmit={handleAdd} className="bg-gray-900 rounded-lg p-4 mb-4 grid grid-cols-2 gap-3">
          <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
            placeholder="协议名称" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <select value={form.chain} onChange={e => setForm({...form, chain: e.target.value})}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
            {CHAINS.map(c => <option key={c}>{c}</option>)}
          </select>
          <input value={form.defillama_slug} onChange={e => setForm({...form, defillama_slug: e.target.value})}
            placeholder="DefiLlama slug" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <input value={form.safety_score} onChange={e => setForm({...form, safety_score: e.target.value})}
            placeholder="安全评分 (0-10)" type="number" step="0.1"
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <button type="submit" className="col-span-2 bg-green-600 hover:bg-green-700 text-white py-2 rounded text-sm">保存</button>
        </form>
      )}

      <div className="space-y-6">
        {groups.map(g => {
          const collapsed = collapsedGroups[g.key];
          const enabledCount = g.protocols.filter(p => p.enabled).length;
          return (
            <section key={g.key}>
              <div className="flex items-center justify-between mb-2 cursor-pointer select-none"
                onClick={() => setCollapsedGroups({ ...collapsedGroups, [g.key]: !collapsed })}>
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 text-xs">{collapsed ? '▶' : '▼'}</span>
                  <h2 className="text-base font-semibold text-gray-300">{g.label}</h2>
                  <span className="text-xs text-gray-500">
                    {enabledCount}/{g.protocols.length}
                  </span>
                </div>
              </div>
              {!collapsed && (
                <div className="space-y-3">
                  {g.protocols.map(p => (
                    <ProtocolCard key={p.id} protocol={p}
                      onToggle={async (id) => { await api.protocols.toggle(id); reload(); }}
                      onDelete={async (id) => { await api.protocols.delete(id); reload(); }}
                    />
                  ))}
                </div>
              )}
            </section>
          );
        })}
        {protocols.length === 0 && <p className="text-gray-500">暂无协议配置，请点击上方"添加协议"</p>}
      </div>
    </div>
  );
}
