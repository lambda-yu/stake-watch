import { useEffect, useState } from 'react';
import { api } from '../api/client';

type Alert = {
  rule_type: string;
  severity: 'critical' | 'warning' | 'info';
  protocol: string;
  chain: string;
  title: string;
  message: string;
  details: any;
  created_at: string;
  dedup_key: string;
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: '严重', warning: '警告', info: '信息',
};
const SEVERITY_COLOR: Record<string, string> = {
  critical: 'text-red-400 border-red-500/40 bg-red-500/10',
  warning:  'text-amber-400 border-amber-500/40 bg-amber-500/10',
  info:     'text-sky-400 border-sky-500/40 bg-sky-500/10',
};

function formatTime(iso: string, tzOffset = 8): string {
  const d = new Date(iso);
  const shifted = new Date(d.getTime() + tzOffset * 3600 * 1000);
  return shifted.toISOString().slice(0, 16).replace('T', ' ') + ` UTC+${tzOffset}`;
}

export function Alerts() {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [filter, setFilter] = useState<'all' | 'critical' | 'warning' | 'info'>('all');
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const reload = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const list = await api.alerts.list(200);
      setAlerts(list);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => { reload(); }, []);

  const filtered = alerts?.filter(a => filter === 'all' || a.severity === filter) ?? [];
  const counts = {
    all: alerts?.length ?? 0,
    critical: alerts?.filter(a => a.severity === 'critical').length ?? 0,
    warning:  alerts?.filter(a => a.severity === 'warning').length ?? 0,
    info:     alerts?.filter(a => a.severity === 'info').length ?? 0,
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <h1 className="text-2xl font-bold">告警记录</h1>
        <button onClick={reload} disabled={refreshing}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white px-4 py-2 rounded text-sm">
          {refreshing ? '刷新中...' : '刷新'}
        </button>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {(['all', 'critical', 'warning', 'info'] as const).map(k => (
          <button key={k} onClick={() => setFilter(k)}
            className={`px-3 py-1.5 rounded text-sm border ${
              filter === k
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-500'
            }`}>
            {k === 'all' ? '全部' : SEVERITY_LABEL[k]} ({counts[k]})
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/40 text-red-400 rounded p-3 mb-4 text-sm">
          加载失败: {error}
        </div>
      )}

      {alerts === null ? (
        <p className="text-gray-500">加载中...</p>
      ) : filtered.length === 0 ? (
        <p className="text-gray-500">暂无{filter === 'all' ? '' : SEVERITY_LABEL[filter]}告警</p>
      ) : (
        <div className="space-y-2">
          {filtered.map((a, i) => (
            <div key={`${a.dedup_key}-${a.created_at}-${i}`}
              className={`border rounded-lg p-4 ${SEVERITY_COLOR[a.severity]}`}>
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-black/30">
                      {SEVERITY_LABEL[a.severity] || a.severity}
                    </span>
                    <span className="text-xs text-gray-500 font-mono">{a.rule_type}</span>
                    <span className="text-xs text-gray-500">·</span>
                    <span className="text-xs text-gray-400">{a.protocol}</span>
                    <span className="text-xs text-gray-500">/ {a.chain || '-'}</span>
                  </div>
                  <div className="font-medium text-gray-100">{a.title}</div>
                  <div className="text-sm text-gray-300 mt-1 break-words">{a.message}</div>
                  {a.details && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-300">
                        详细数据
                      </summary>
                      <pre className="mt-1 text-xs text-gray-400 bg-black/40 p-2 rounded overflow-x-auto">
{JSON.stringify(a.details, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
                <div className="text-xs text-gray-500 whitespace-nowrap">
                  {formatTime(a.created_at)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
