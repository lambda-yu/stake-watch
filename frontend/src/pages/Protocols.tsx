import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { ProtocolCard } from '../components/ProtocolCard';

const CHAINS = ['base', 'ethereum', 'solana', 'bsc'];

export function Protocols() {
  const [protocols, setProtocols] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', chain: 'base', collector: 'defillama', defillama_slug: '', safety_score: '' });

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

  return (
    <div className="max-w-4xl">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Protocols</h1>
        <button onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm">
          {showForm ? 'Cancel' : 'Add Protocol'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleAdd} className="bg-gray-900 rounded-lg p-4 mb-4 grid grid-cols-2 gap-3">
          <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
            placeholder="Protocol name" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <select value={form.chain} onChange={e => setForm({...form, chain: e.target.value})}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
            {CHAINS.map(c => <option key={c}>{c}</option>)}
          </select>
          <input value={form.defillama_slug} onChange={e => setForm({...form, defillama_slug: e.target.value})}
            placeholder="DefiLlama slug" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <input value={form.safety_score} onChange={e => setForm({...form, safety_score: e.target.value})}
            placeholder="Safety score (0-10)" type="number" step="0.1"
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          <button type="submit" className="col-span-2 bg-green-600 hover:bg-green-700 text-white py-2 rounded text-sm">Save</button>
        </form>
      )}

      <div className="space-y-3">
        {protocols.map(p => (
          <ProtocolCard key={p.id} protocol={p}
            onToggle={async (id) => { await api.protocols.toggle(id); reload(); }}
            onDelete={async (id) => { await api.protocols.delete(id); reload(); }}
          />
        ))}
        {protocols.length === 0 && <p className="text-gray-500">No protocols configured. Add one above.</p>}
      </div>
    </div>
  );
}
