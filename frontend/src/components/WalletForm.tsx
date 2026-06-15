import { useState } from 'react';

type Props = { onAdd: (wallet: { chain: string; address: string; label?: string }) => void };
const CHAINS = ['base', 'ethereum', 'solana', 'bsc'];

export function WalletForm({ onAdd }: Props) {
  const [chain, setChain] = useState('base');
  const [address, setAddress] = useState('');
  const [label, setLabel] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!address.trim()) return;
    onAdd({ chain, address: address.trim(), label: label.trim() || undefined });
    setAddress('');
    setLabel('');
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 items-end">
      <select value={chain} onChange={e => setChain(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
        {CHAINS.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <input value={address} onChange={e => setAddress(e.target.value)}
        placeholder="Wallet address" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm flex-1" />
      <input value={label} onChange={e => setLabel(e.target.value)}
        placeholder="Label (optional)" className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-40" />
      <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm">Add</button>
    </form>
  );
}
