import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { WalletForm } from '../components/WalletForm';

export function Settings() {
  const [wallets, setWallets] = useState<any[]>([]);
  const [intervals, setIntervals] = useState<any>({});
  const [risk, setRisk] = useState<any>({});

  const reload = async () => {
    try {
      setWallets(await api.wallets.list());
      setIntervals(await api.intervals.get());
      setRisk(await api.risk.get());
    } catch {}
  };
  useEffect(() => { reload(); }, []);

  const addWallet = async (data: any) => { await api.wallets.add(data); reload(); };
  const deleteWallet = async (id: number) => { await api.wallets.delete(id); reload(); };
  const updateInterval = async (key: string, value: number) => { await api.intervals.update({ [key]: value }); reload(); };
  const updateRisk = async (key: string, value: number) => { await api.risk.update({ [key]: value }); reload(); };

  return (
    <div className="space-y-8 max-w-4xl">
      <section>
        <h2 className="text-xl font-semibold mb-3">Wallets</h2>
        <WalletForm onAdd={addWallet} />
        <div className="mt-3 space-y-2">
          {wallets.map(w => (
            <div key={w.id} className="flex items-center justify-between bg-gray-900 rounded p-3">
              <div>
                <span className="text-xs bg-gray-700 px-2 py-0.5 rounded mr-2">{w.chain}</span>
                <span className="font-mono text-sm">{w.address}</span>
                {w.label && <span className="text-gray-500 ml-2 text-sm">{w.label}</span>}
              </div>
              <button onClick={() => deleteWallet(w.id)} className="text-red-400 hover:text-red-300 text-sm">Remove</button>
            </div>
          ))}
          {wallets.length === 0 && <p className="text-gray-500 text-sm">No wallets configured.</p>}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">Polling Intervals (seconds)</h2>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(intervals).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-sm text-gray-400 w-40">{key}</label>
              <input type="number" value={val as number}
                onChange={e => updateInterval(key, Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm w-24" />
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">Risk Thresholds</h2>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(risk).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-sm text-gray-400 w-48">{key}</label>
              <input type="number" step="0.01" value={val as number}
                onChange={e => updateRisk(key, Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm w-24" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
