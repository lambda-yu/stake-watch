import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { ProtocolCard } from '../components/ProtocolCard';

const CHAINS = ['base', 'ethereum', 'solana', 'bsc'];

export function Protocols() {
  const [protocols, setProtocols] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', chain: 'base', collector: 'defillama', defillama_slug: '', safety_score: '' });
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<any>(null);

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

      <div className="space-y-3">
        {protocols.map(p => (
          <ProtocolCard key={p.id} protocol={p}
            onToggle={async (id) => { await api.protocols.toggle(id); reload(); }}
            onDelete={async (id) => { await api.protocols.delete(id); reload(); }}
          />
        ))}
        {protocols.length === 0 && <p className="text-gray-500">暂无协议配置，请点击上方"添加协议"</p>}
      </div>
    </div>
  );
}
