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

const COLLECTORS = ['defillama', 'morpho', 'aave_v3', 'compound_v3', 'sky_susds', 'kamino'];
const PROTOCOL_TYPES = ['lending', 'savings', 'vault'];

type EditForm = {
  name: string; chain: string; collector: string;
  defillama_slug: string; safety_score: string;
  vault_address: string; pool_filter: string;
  protocol_type: string; reference_apy: string;
  safety_rank: string; primary_risks: string;
};

const EMPTY_FORM: EditForm = {
  name: '', chain: 'base', collector: 'defillama',
  defillama_slug: '', safety_score: '',
  vault_address: '', pool_filter: '', protocol_type: '',
  reference_apy: '', safety_rank: '', primary_risks: '',
};

export function Protocols() {
  const [protocols, setProtocols] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<EditForm>(EMPTY_FORM);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<any>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [reportConfig, setReportConfig] = useState<{ interval: number; enabled: boolean }>({ interval: 14400, enabled: true });
  const [sendingReport, setSendingReport] = useState(false);
  const [reportResult, setReportResult] = useState<{ success: boolean; error?: string } | null>(null);
  const [refreshConfig, setRefreshConfig] = useState<{ interval: number; enabled: boolean }>({ interval: 3600, enabled: true });
  const [refreshConfigNote, setRefreshConfigNote] = useState<string | null>(null);

  const reload = async () => { try { setProtocols(await api.protocols.list()); } catch {} };
  useEffect(() => {
    reload();
    api.protocols.reportConfig().then(setReportConfig).catch(() => {});
    api.protocols.refreshConfig().then(setRefreshConfig).catch(() => {});
  }, []);

  const saveRefreshConfig = async (patch: { interval?: number; enabled?: boolean }) => {
    setRefreshConfigNote(null);
    try {
      const r = await api.protocols.updateRefreshConfig(patch);
      setRefreshConfig({ interval: r.interval, enabled: r.enabled });
      const hr = r.hot_reload;
      setRefreshConfigNote(
        hr === 'scheduled' ? '✓ 已保存，自动刷新已启用'
        : hr === 'removed' ? '✓ 已保存，自动刷新已停用'
        : hr === 'disabled' ? '✓ 已保存'
        : hr ? `✓ 已保存（${hr}）`
        : '✓ 已保存'
      );
    } catch (e: any) {
      setRefreshConfigNote(`✗ 保存失败: ${e.message}`);
    }
  };

  const buildPayload = (): any => {
    const risks = form.primary_risks
      .split(',').map(s => s.trim()).filter(Boolean);
    const payload: any = {
      chain: form.chain, collector: form.collector,
      defillama_slug: form.defillama_slug || null,
      safety_score: form.safety_score ? Number(form.safety_score) : null,
      safety_rank: form.safety_rank ? Number(form.safety_rank) : null,
      reference_apy: form.reference_apy || null,
      vault_address: form.vault_address || null,
      pool_filter: form.pool_filter || null,
      protocol_type: form.protocol_type || null,
      primary_risks: risks,
    };
    return payload;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (editingId !== null) {
      await api.protocols.update(editingId, buildPayload());
    } else {
      await api.protocols.add({ ...buildPayload(), name: form.name, enabled: true });
    }
    setForm(EMPTY_FORM);
    setShowForm(false);
    setEditingId(null);
    reload();
  };

  const startEdit = (p: any) => {
    setEditingId(p.id);
    setForm({
      name: p.name,
      chain: p.chain || 'base',
      collector: p.collector || 'defillama',
      defillama_slug: p.defillama_slug || '',
      safety_score: p.safety_score !== null && p.safety_score !== undefined ? String(p.safety_score) : '',
      safety_rank: p.safety_rank !== null && p.safety_rank !== undefined ? String(p.safety_rank) : '',
      reference_apy: p.reference_apy || '',
      vault_address: p.vault_address || '',
      pool_filter: p.pool_filter || '',
      protocol_type: p.protocol_type || '',
      primary_risks: Array.isArray(p.primary_risks) ? p.primary_risks.join(', ') : '',
    });
    setShowForm(true);
    // Scroll to top so the form is visible
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const cancelEdit = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowForm(false);
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
        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-lg p-4 mb-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-300">
              {editingId !== null ? `编辑协议 · ${form.name}` : '添加协议'}
            </h3>
            {editingId !== null && (
              <span className="text-xs text-gray-500">编辑模式不能修改名称</span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">协议名称 <span className="text-red-400">*</span></label>
              <input value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                disabled={editingId !== null}
                placeholder="e.g. aave_v3_base"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm disabled:opacity-50 font-mono" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">主链</label>
              <select value={form.chain}
                onChange={e => setForm({ ...form, chain: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
                {CHAINS.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Collector</label>
              <select value={form.collector}
                onChange={e => setForm({ ...form, collector: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
                {COLLECTORS.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">协议类型</label>
              <select value={form.protocol_type}
                onChange={e => setForm({ ...form, protocol_type: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
                <option value="">-</option>
                {PROTOCOL_TYPES.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">DefiLlama slug</label>
              <input value={form.defillama_slug}
                onChange={e => setForm({ ...form, defillama_slug: e.target.value })}
                placeholder="e.g. aave-v3"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm font-mono" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Vault 地址（Morpho 必填）</label>
              <input value={form.vault_address}
                onChange={e => setForm({ ...form, vault_address: e.target.value })}
                placeholder="0x..."
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm font-mono" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Pool symbol 过滤（可选）</label>
              <input value={form.pool_filter}
                onChange={e => setForm({ ...form, pool_filter: e.target.value })}
                placeholder="e.g. STEAKUSDC"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm font-mono" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">参考 APY 标注（可选）</label>
              <input value={form.reference_apy}
                onChange={e => setForm({ ...form, reference_apy: e.target.value })}
                placeholder="e.g. 4-6%"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">安全评分 (0-10)</label>
              <input value={form.safety_score}
                onChange={e => setForm({ ...form, safety_score: e.target.value })}
                placeholder="8.5" type="number" step="0.1"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">安全排名（数字，越小越安全）</label>
              <input value={form.safety_rank}
                onChange={e => setForm({ ...form, safety_rank: e.target.value })}
                placeholder="1" type="number"
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">
              主要风险点（逗号分隔）
            </label>
            <input value={form.primary_risks}
              onChange={e => setForm({ ...form, primary_risks: e.target.value })}
              placeholder="共享流动池, 利用率, Base L2 风险"
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm" />
          </div>

          <div className="flex gap-2">
            <button type="submit"
              className="flex-1 bg-green-600 hover:bg-green-700 text-white py-2 rounded text-sm">
              {editingId !== null ? '保存修改' : '添加'}
            </button>
            <button type="button" onClick={cancelEdit}
              className="px-6 bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 py-2 rounded text-sm">
              取消
            </button>
          </div>
        </form>
      )}

      <div className="bg-gray-900 rounded-lg p-6 mb-4">
        <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
          <h2 className="text-lg font-semibold">自动刷新数据</h2>
          {refreshConfigNote && (
            <span className={`text-xs ${refreshConfigNote.startsWith('✓') ? 'text-green-400' : 'text-red-400'}`}>
              {refreshConfigNote}
            </span>
          )}
        </div>
        <p className="text-gray-500 text-sm mb-4">
          定时拉取所有启用协议的 APY / TVL 到数据库，驱动"协议对比"页数据（独立于 Telegram 推送，修改立即生效）。
        </p>
        <div className="flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={refreshConfig.enabled}
              onChange={e => saveRefreshConfig({ enabled: e.target.checked })}
              className="w-4 h-4 rounded bg-gray-800 border-gray-600" />
            <span className="text-sm">启用自动刷新</span>
          </label>
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-400">刷新间隔</label>
            <select value={refreshConfig.interval}
              onChange={e => saveRefreshConfig({ interval: Number(e.target.value) })}
              disabled={!refreshConfig.enabled}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm disabled:opacity-50">
              <option value={300}>5 分钟</option>
              <option value={600}>10 分钟</option>
              <option value={1800}>30 分钟</option>
              <option value={3600}>1 小时</option>
              <option value={7200}>2 小时</option>
              <option value={14400}>4 小时</option>
              <option value={21600}>6 小时</option>
              <option value={43200}>12 小时</option>
            </select>
          </div>
        </div>
      </div>

      <div className="bg-gray-900 rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold mb-2">定时报告推送</h2>
        <p className="text-gray-500 text-sm mb-4">定时将所有启用协议的 APY 和 TVL 推送到 Telegram</p>

        <div className="space-y-4">
          <div className="flex items-center gap-4 flex-wrap">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={reportConfig.enabled}
                onChange={async e => {
                  const enabled = e.target.checked;
                  const r = await api.protocols.updateReportConfig({ enabled });
                  setReportConfig(r);
                }}
                className="w-4 h-4 rounded bg-gray-800 border-gray-600" />
              <span className="text-sm">启用定时推送</span>
            </label>
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-400">推送间隔</label>
              <select value={reportConfig.interval}
                onChange={async e => { setReportConfig(await api.protocols.updateReportConfig({ interval: Number(e.target.value) })); }}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
                <option value={1800}>30 分钟</option>
                <option value={3600}>1 小时</option>
                <option value={7200}>2 小时</option>
                <option value={14400}>4 小时</option>
                <option value={21600}>6 小时</option>
                <option value={43200}>12 小时</option>
                <option value={86400}>24 小时</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={async () => {
                setSendingReport(true); setReportResult(null);
                try {
                  const r = await api.protocols.sendReport();
                  setReportResult(r);
                } catch (e: any) {
                  setReportResult({ success: false, error: e.message });
                } finally { setSendingReport(false); }
              }}
              disabled={sendingReport}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white px-4 py-2 rounded text-sm"
            >
              {sendingReport ? '发送中...' : '立即发送报告'}
            </button>
            {reportResult && (
              <span className={`text-sm ${reportResult.success ? 'text-green-400' : 'text-red-400'}`}>
                {reportResult.success ? '已发送' : `失败: ${reportResult.error}`}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500">提示: 设置后需重启服务生效；手动发送随时可用</p>
        </div>
      </div>

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
                      onEdit={() => startEdit(p)}
                      onReevaluate={async (id) => { await api.protocols.evaluate(id); reload(); }}
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
