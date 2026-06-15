type Protocol = {
  id: number; name: string; chain: string; collector: string;
  enabled: boolean; safety_score: number | null; reference_apy: string | null;
  primary_risks: string[];
};
type Props = { protocol: Protocol; onToggle: (id: number) => void; onDelete: (id: number) => void };

export function ProtocolCard({ protocol: p, onToggle, onDelete }: Props) {
  return (
    <div className={`bg-gray-900 rounded-lg p-4 border ${p.enabled ? 'border-gray-700' : 'border-gray-800 opacity-60'}`}>
      <div className="flex justify-between items-start">
        <div>
          <h3 className="font-semibold">{p.name}</h3>
          <div className="flex gap-2 mt-1">
            <span className="text-xs bg-gray-700 px-2 py-0.5 rounded">{p.chain}</span>
            {p.safety_score && <span className="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded">{p.safety_score}/10</span>}
            {p.reference_apy && <span className="text-xs bg-blue-900 text-blue-300 px-2 py-0.5 rounded">{p.reference_apy}</span>}
          </div>
          {p.primary_risks.length > 0 && (
            <div className="mt-2 text-xs text-gray-500">{p.primary_risks.join(' / ')}</div>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={() => onToggle(p.id)}
            className={`text-xs px-3 py-1 rounded ${p.enabled ? 'bg-green-800 text-green-200' : 'bg-gray-700 text-gray-400'}`}>
            {p.enabled ? 'Enabled' : 'Disabled'}
          </button>
          <button onClick={() => onDelete(p.id)} className="text-xs text-red-400 hover:text-red-300">Delete</button>
        </div>
      </div>
    </div>
  );
}
