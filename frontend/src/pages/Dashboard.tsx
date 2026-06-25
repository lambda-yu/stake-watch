import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

type Protocol = {
  id: number;
  name: string;
  chain: string;
  enabled: boolean;
  risk_total?: number;
  risk_level?: string;
  primary_chain?: string;
  primary_asset?: string;
  live_risk?: {
    total: number;
    level: string;
    veto_flags: string[];
    evaluated_at: string;
  } | null;
};
type Alert = {
  severity: 'critical' | 'warning' | 'info';
  protocol: string;
  chain: string;
  title: string;
  message: string;
  created_at: string;
};
type Status = {
  status: string;
  version: string;
  now: string;
  protocols: { total: number; enabled: number };
  data: { positions: number; tvl_snapshots: number;
          last_collection: string | null; last_collection_age_seconds: number | null };
  alerts: { critical_total: number; last_alert_at: string | null;
            last_alert_age_seconds: number | null };
};

const LEVEL_COLOR: Record<string, string> = {
  A: 'text-green-400', B: 'text-emerald-300',
  C: 'text-yellow-400', D: 'text-orange-400', E: 'text-red-400',
};
const SEVERITY_COLOR: Record<string, string> = {
  critical: 'text-red-400 border-red-500/40 bg-red-500/10',
  warning:  'text-amber-400 border-amber-500/40 bg-amber-500/10',
  info:     'text-sky-400 border-sky-500/40 bg-sky-500/10',
};

function ageHuman(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${seconds} 秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

export function Dashboard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [protocols, setProtocols] = useState<Protocol[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.status.get(),
      api.protocols.list(),
      api.alerts.list(10).catch(() => []),
    ])
      .then(([s, p, a]) => { setStatus(s); setProtocols(p); setAlerts(a); })
      .catch(e => setErr(e.message));
  }, []);

  const effectiveScore = (p: Protocol) =>
    p.live_risk?.total ?? p.risk_total ?? 0;
  const effectiveLevel = (p: Protocol) =>
    p.live_risk?.level ?? p.risk_level ?? 'A';
  const topRisks = [...protocols]
    .filter(p => p.enabled && typeof effectiveScore(p) === 'number')
    .sort((a, b) => effectiveScore(b) - effectiveScore(a))
    .slice(0, 5);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">仪表盘</h1>

      {err && (
        <div className="bg-red-500/10 border border-red-500/40 text-red-400 rounded p-3 mb-4 text-sm">
          {err}
        </div>
      )}

      {/* Status strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Card label="启用协议" value={status ? `${status.protocols.enabled}/${status.protocols.total}` : '—'} />
        <Card label="最近采集" value={status ? ageHuman(status.data.last_collection_age_seconds) : '—'} />
        <Card label="历史告警 (CRITICAL)" value={status?.alerts.critical_total ?? '—'}
              accent={status && status.alerts.critical_total > 0 ? 'text-red-400' : undefined} />
        <Card label="TVL 快照点数" value={status?.data.tvl_snapshots ?? '—'} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Top-risk panel */}
        <section className="bg-gray-900 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">风险最高的协议</h2>
            <Link to="/protocols" className="text-xs text-blue-400 hover:underline">全部 →</Link>
          </div>
          {topRisks.length === 0 ? (
            <p className="text-gray-500 text-sm">尚无评估数据</p>
          ) : (
            <ul className="space-y-2">
              {topRisks.map(p => (
                <li key={p.id} className="flex items-center justify-between text-sm">
                  <div className="min-w-0">
                    <span className="font-mono text-gray-200 truncate">{p.name}</span>
                    <span className="text-xs text-gray-500 ml-2">
                      {p.primary_chain ?? p.chain} / {p.primary_asset ?? 'USDC'}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 whitespace-nowrap">
                    {p.live_risk && (
                      <span className="text-[9px] uppercase text-gray-500" title="live (含链上信号)">live</span>
                    )}
                    <span className={`text-xs font-bold ${LEVEL_COLOR[effectiveLevel(p)]}`}>
                      {effectiveLevel(p)}
                    </span>
                    <span className="text-gray-400 tabular-nums">
                      {effectiveScore(p).toFixed(1)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Recent alerts panel */}
        <section className="bg-gray-900 rounded-lg p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">最近告警</h2>
            <Link to="/alerts" className="text-xs text-blue-400 hover:underline">全部 →</Link>
          </div>
          {alerts.length === 0 ? (
            <p className="text-gray-500 text-sm">暂无告警</p>
          ) : (
            <ul className="space-y-2">
              {alerts.slice(0, 5).map((a, i) => (
                <li key={i} className={`text-sm border rounded p-2 ${SEVERITY_COLOR[a.severity] || ''}`}>
                  <div className="font-medium text-gray-100 truncate">{a.title}</div>
                  <div className="flex items-center gap-2 text-xs text-gray-500 mt-1">
                    <span className="font-mono">{a.protocol}</span>
                    <span>·</span>
                    <span>{new Date(a.created_at).toLocaleString('zh-CN', { hour12: false })}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="mt-6 text-xs text-gray-500 text-center">
        系统{status?.status === 'running' ? '运行中' : status?.status || '正在连接...'}
        {status && ` · v${status.version}`}
      </div>
    </div>
  );
}

function Card({ label, value, accent }:
                { label: string; value: string | number; accent?: string }) {
  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-xl font-semibold tabular-nums ${accent || 'text-gray-100'}`}>
        {value}
      </div>
    </div>
  );
}
