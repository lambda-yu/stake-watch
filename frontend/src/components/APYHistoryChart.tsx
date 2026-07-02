import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';

type Point = { t: string; apy: number; tvl_usd: number };
type Series = { chain: string; asset: string; points: Point[] };

const SERIES_COLORS = [
  '#60a5fa', // blue
  '#34d399', // green
  '#f59e0b', // amber
  '#f472b6', // pink
  '#a78bfa', // violet
  '#22d3ee', // cyan
];

type Props = { protocolId: number };

const SOURCE_LABELS: Record<string, { label: string; color: string; hint: string }> = {
  morpho:    { label: 'Morpho 官方', color: 'text-purple-400',
              hint: 'Morpho GraphQL historicalState (per-vault, 权威源)' },
  defillama: { label: 'DefiLlama', color: 'text-emerald-400',
              hint: 'DefiLlama /chart 聚合（每日粒度，最长 ~1 年）' },
  snapshots: { label: '本地快照', color: 'text-amber-400',
              hint: '本地采集（4h 粒度，从安装起累积）' },
  empty:     { label: '无数据', color: 'text-gray-500', hint: '' },
};

export function APYHistoryChart({ protocolId }: Props) {
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [source, setSource] = useState<'auto' | 'official' | 'local'>('auto');
  const [series, setSeries] = useState<Series[] | null>(null);
  const [usedSource, setUsedSource] = useState<string>('empty');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.protocols.history(protocolId, days, source)
      .then(r => {
        if (!cancelled) { setSeries(r.series); setUsedSource(r.source); }
      })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [protocolId, days, source]);

  const totalPoints = series?.reduce((n, s) => n + s.points.length, 0) ?? 0;
  const srcMeta = SOURCE_LABELS[usedSource] || SOURCE_LABELS.empty;

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
        <div className="flex gap-1">
          {([7, 30, 90] as const).map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`text-xs px-2 py-1 rounded ${
                days === d ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}>
              {d} 天
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <select value={source} onChange={e => setSource(e.target.value as any)}
            title="数据源"
            className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300">
            <option value="auto">自动</option>
            <option value="official">官方 (DefiLlama)</option>
            <option value="local">本地快照</option>
          </select>
          {series && series.length > 0 && (
            <span className={`text-xs ${srcMeta.color}`} title={srcMeta.hint}>
              {srcMeta.label}
            </span>
          )}
          <span className="text-xs text-gray-500">
            {loading ? '加载中...' : `${totalPoints} 点`}
          </span>
        </div>
      </div>

      {error && <p className="text-xs text-red-400">加载失败: {error}</p>}

      {!loading && !error && series && series.length === 0 && (
        <p className="text-xs text-gray-500">
          {source === 'official'
            ? '官方数据源未匹配到此协议 — 请检查 DefiLlama slug / pool_filter 配置'
            : source === 'local'
              ? '本地快照尚未累积到数据（每 4h 采一次，首次运行需等一两个周期）'
              : '暂无历史数据'}
        </p>
      )}

      {series && series.length > 0 && (
        <LineChart series={series} days={days} />
      )}
    </div>
  );
}


function LineChart({ series, days }: { series: Series[]; days: number }) {
  const width = 560;
  const height = 180;
  const padTop = 8;
  const padRight = 8;
  const padBottom = 22;
  const padLeft = 40;

  const { xMin, xMax, yMin, yMax, allPoints } = useMemo(() => {
    const all = series.flatMap(s => s.points.map(p => ({
      x: new Date(p.t).getTime(),
      y: p.apy,
    })));
    const now = Date.now();
    const xMin = now - days * 86400 * 1000;
    const xMax = now;
    if (!all.length) {
      return { xMin, xMax, yMin: 0, yMax: 10, allPoints: all };
    }
    const ys = all.map(p => p.y);
    let ymin = Math.min(...ys);
    let ymax = Math.max(...ys);
    // Pad range so lines don't touch the edges
    const span = Math.max(0.5, ymax - ymin);
    ymin = Math.max(0, ymin - span * 0.15);
    ymax = ymax + span * 0.15;
    return { xMin, xMax, yMin: ymin, yMax: ymax, allPoints: all };
  }, [series, days]);

  const xToPx = (x: number) => padLeft + ((x - xMin) / (xMax - xMin)) * (width - padLeft - padRight);
  const yToPx = (y: number) => padTop + (1 - (y - yMin) / (yMax - yMin)) * (height - padTop - padBottom);

  const yTicks = useMemo(() => {
    const tickCount = 4;
    const step = (yMax - yMin) / tickCount;
    return Array.from({ length: tickCount + 1 }, (_, i) => yMin + step * i);
  }, [yMin, yMax]);

  const xTicks = useMemo(() => {
    // 4 evenly-spaced date labels
    return [0, 0.33, 0.66, 1].map(f => xMin + (xMax - xMin) * f);
  }, [xMin, xMax]);

  const fmtDate = (ts: number) => {
    const d = new Date(ts);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
      {/* Y grid + labels */}
      {yTicks.map((v, i) => {
        const y = yToPx(v);
        return (
          <g key={i}>
            <line x1={padLeft} y1={y} x2={width - padRight} y2={y}
              stroke="#374151" strokeWidth="0.5" strokeDasharray="2 3" />
            <text x={padLeft - 4} y={y + 3} fill="#9ca3af" fontSize="10"
              textAnchor="end">{v.toFixed(1)}%</text>
          </g>
        );
      })}

      {/* X labels */}
      {xTicks.map((v, i) => (
        <text key={i} x={xToPx(v)} y={height - 6} fill="#9ca3af" fontSize="10"
          textAnchor="middle">{fmtDate(v)}</text>
      ))}

      {/* Series */}
      {series.map((s, si) => {
        const color = SERIES_COLORS[si % SERIES_COLORS.length];
        if (s.points.length === 0) return null;
        const d = s.points.map((p, i) => {
          const x = xToPx(new Date(p.t).getTime());
          const y = yToPx(p.apy);
          return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(' ');
        return (
          <g key={`${s.chain}-${s.asset}`}>
            <path d={d} fill="none" stroke={color} strokeWidth="1.5"
              strokeLinejoin="round" strokeLinecap="round" />
            {/* Dot at latest point */}
            {s.points.length > 0 && (() => {
              const last = s.points[s.points.length - 1];
              return (
                <circle cx={xToPx(new Date(last.t).getTime())}
                  cy={yToPx(last.apy)} r="2.5" fill={color} />
              );
            })()}
          </g>
        );
      })}

      {/* Legend */}
      <g transform={`translate(${padLeft}, ${padTop})`}>
        {series.map((s, si) => (
          <g key={`${s.chain}-${s.asset}`} transform={`translate(${si * 90}, 0)`}>
            <rect x="0" y="0" width="10" height="2"
              fill={SERIES_COLORS[si % SERIES_COLORS.length]} />
            <text x="14" y="4" fill="#e5e7eb" fontSize="10">
              {s.chain} · {s.asset}
              {s.points.length > 0 && (
                <tspan fill="#9ca3af"> {s.points[s.points.length - 1].apy.toFixed(2)}%</tspan>
              )}
            </text>
          </g>
        ))}
      </g>

      {allPoints.length === 0 && (
        <text x={width / 2} y={height / 2} fill="#6b7280" fontSize="12"
          textAnchor="middle">暂无数据</text>
      )}
    </svg>
  );
}
