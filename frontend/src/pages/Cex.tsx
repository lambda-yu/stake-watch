import { useEffect, useMemo, useState } from 'react';
import { api, type CexVenue, type CexRate } from '../api/client';

const pct = (x: number) => (x * 100).toFixed(2) + '%';

const rangeText = (r: CexRate) =>
  r.apy_min === r.apy_max ? pct(r.apy_max) : `${pct(r.apy_min)}–${pct(r.apy_max)}`;

const minAgo = (iso: string) =>
  Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));

export function Cex() {
  const [rates, setRates] = useState<CexRate[]>([]);
  const [venues, setVenues] = useState<CexVenue[]>([]);
  const [sortDesc, setSortDesc] = useState(true);
  const [manageOpen, setManageOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [flash, setFlash] = useState<{ ok: boolean; msg: string } | null>(null);

  const refresh = () => {
    api.cex.latestRates().then(setRates).catch(() => {});
    api.cex.venues().then(setVenues).catch(() => {});
  };
  useEffect(refresh, []);

  const manualRefresh = async () => {
    setRefreshing(true);
    setFlash(null);
    try {
      const r = await api.cex.refresh();
      refresh();
      const errNote = r.errors.length ? `,${r.errors.length} 个错误` : '';
      setFlash({
        ok: true,
        msg: `已刷新 ${r.venues_refreshed} 个 venue,写入 ${r.rates_written} 条${errNote}`,
      });
    } catch (e: unknown) {
      setFlash({ ok: false, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setRefreshing(false);
    }
  };

  const oldestMin = useMemo(
    () => rates.length ? Math.max(...rates.map(r => minAgo(r.updated_at))) : null,
    [rates]
  );

  const sorted = useMemo(
    () => [...rates].sort((a, b) => (b.apy_max - a.apy_max) * (sortDesc ? 1 : -1)),
    [rates, sortDesc]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">CEX Earn 利率</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">
            {oldestMin !== null ? `${oldestMin} 分钟前刷新` : '暂无数据'}
          </span>
          <button
            onClick={manualRefresh}
            disabled={refreshing}
            className="text-sm px-3 py-1 rounded border border-blue-500/50
                       text-blue-300 hover:bg-blue-500/10
                       disabled:opacity-50 disabled:cursor-not-allowed">
            {refreshing ? '刷新中…' : '手动刷新'}
          </button>
        </div>
      </div>

      {flash && (
        <div className={`text-sm px-3 py-2 rounded border ${
          flash.ok
            ? 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10'
            : 'text-red-300 border-red-500/40 bg-red-500/10'
        }`}>
          {flash.msg}
        </div>
      )}

      <div className="border border-gray-800 rounded overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-900">
            <tr className="text-left text-gray-400">
              <th className="px-3 py-2">Venue</th>
              <th className="px-3 py-2">Asset</th>
              <th className="px-3 py-2 cursor-pointer select-none"
                  onClick={() => setSortDesc(s => !s)}>
                Flexible APY {sortDesc ? '▼' : '▲'}
              </th>
              <th className="px-3 py-2">分档</th>
              <th className="px-3 py-2">Updated</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-gray-500">
                  暂无 CEX 利率数据。首次刷新可能需要几分钟。
                </td>
              </tr>
            )}
            {sorted.map(r => (
              <tr key={`${r.venue}-${r.asset}-${r.product_type}`}
                  className="border-t border-gray-900">
                <td className="px-3 py-2">{r.venue_display}</td>
                <td className="px-3 py-2">{r.asset}</td>
                <td className="px-3 py-2 font-mono">{rangeText(r)}</td>
                <td className="px-3 py-2 text-gray-400"
                    title={r.tier_note ?? ''}>
                  {r.tier_note ? '悬停查看' : '—'}
                </td>
                <td className="px-3 py-2 text-gray-500">{minAgo(r.updated_at)}m ago</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button onClick={() => setManageOpen(o => !o)}
              className="text-sm text-blue-400 hover:text-blue-300">
        {manageOpen ? '收起' : '管理 venues ▸'}
      </button>

      {manageOpen && (
        <div className="space-y-2 border-t border-gray-800 pt-4">
          {venues.map(v => (
            <label key={v.name}
                   className="flex items-center gap-3 py-1 text-sm">
              <input type="checkbox" checked={v.enabled} onChange={async e => {
                await api.cex.patchVenue(v.name, { enabled: e.target.checked });
                refresh();
              }} />
              <span className="w-28 font-medium">{v.display_name}</span>
              <span className="text-gray-500">{v.assets.join(', ')}</span>
              {v.notes && (
                <span className="text-xs text-yellow-500 ml-2">⚠ {v.notes}</span>
              )}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}