import { useEffect, useState } from 'react';
import { api } from '../api/client';

const RISK_COLORS: Record<string, string> = {
  safe: 'bg-green-900/50 text-green-300 border-green-800',
  watch: 'bg-yellow-900/50 text-yellow-300 border-yellow-800',
  caution: 'bg-orange-900/50 text-orange-300 border-orange-800',
  danger: 'bg-red-900/50 text-red-300 border-red-800',
  critical: 'bg-red-900 text-red-200 border-red-600',
};

const RISK_LABELS: Record<string, string> = {
  safe: '安全', watch: '关注', caution: '注意', danger: '危险', critical: '严重',
};

const DEPEG_THRESHOLDS = [
  { range: '0.998 ~ 1.002', status: '正常', color: 'text-green-400', action: '无需操作' },
  { range: '0.995 ~ 0.998', status: '关注', color: 'text-yellow-400', action: '提高采样频率' },
  { range: '0.990 ~ 0.995', status: '预警', color: 'text-orange-400', action: '暂停新增仓位' },
  { range: '0.980 ~ 0.990', status: '高风险', color: 'text-red-400', action: '开始降低敞口' },
  { range: '< 0.980', status: '严重', color: 'text-red-300', action: '优先退出相关池子' },
];

export function Stablecoins() {
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [riskConfig, setRiskConfig] = useState<any>({});
  const [intervals, setIntervals] = useState<any>({});
  const [reportConfig, setReportConfig] = useState<{ interval: number; enabled: boolean }>({ interval: 3600, enabled: true });
  const [sendingReport, setSendingReport] = useState(false);
  const [reportResult, setReportResult] = useState<{ success: boolean; error?: string } | null>(null);

  const [collecting, setCollecting] = useState(false);
  const [dexPools, setDexPools] = useState<any[]>([]);
  const [reserves, setReserves] = useState<any[]>([]);
  const [fetchingReserves, setFetchingReserves] = useState(false);
  const [reserveFetchResult, setReserveFetchResult] = useState<any>(null);

  useEffect(() => {
    api.stablecoins.snapshots().then(setSnapshots).catch(() => {});
    api.risk.get().then(setRiskConfig).catch(() => {});
    api.intervals.get().then(setIntervals).catch(() => {});
    api.stablecoins.reportConfig().then(setReportConfig).catch(() => {});
    api.stablecoins.dexPools().then(setDexPools).catch(() => {});
    api.stablecoins.reserves().then(setReserves).catch(() => {});
  }, []);

  const updateRisk = async (key: string, value: number) => {
    await api.risk.update({ [key]: value });
    setRiskConfig(await api.risk.get());
  };

  const updateInterval = async (key: string, value: number) => {
    await api.intervals.update({ [key]: value });
    setIntervals(await api.intervals.get());
  };

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">稳定币监控</h1>
        <button
          onClick={async () => {
            setCollecting(true);
            try {
              await api.stablecoins.collect();
              setSnapshots(await api.stablecoins.snapshots());
            } catch {} finally { setCollecting(false); }
          }}
          disabled={collecting}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white px-4 py-2 rounded text-sm"
        >
          {collecting ? '采集中...' : '立即采集'}
        </button>
      </div>

      {/* Current Status */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {['USDC', 'USDT'].map(token => {
          const snap = snapshots.find(s => s.token === token);
          const riskClass = snap ? RISK_COLORS[snap.risk_level] || RISK_COLORS.safe : 'bg-gray-800 text-gray-400 border-gray-700';
          return (
            <div key={token} className={`rounded-lg p-5 border ${riskClass}`}>
              <div className="flex justify-between items-start mb-3">
                <h3 className="text-lg font-bold">{token}</h3>
                {snap && (
                  <span className="text-xs px-2 py-0.5 rounded bg-black/20">
                    {RISK_LABELS[snap.risk_level] || snap.risk_level}
                    {snap.risk_score > 0 && ` ${snap.risk_score}/100`}
                  </span>
                )}
              </div>
              {snap ? (
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="opacity-70">价格</span>
                    <span className="font-mono">${snap.price?.toFixed(4)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="opacity-70">偏离</span>
                    <span className="font-mono">{(snap.deviation * 100)?.toFixed(3)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="opacity-70">总供应量</span>
                    <span className="font-mono">${(Number(snap.total_supply) / 1e9)?.toFixed(1)}B</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="opacity-70">24h 供应变化</span>
                    <span className={`font-mono ${snap.supply_change_24h_pct < 0 ? 'text-red-400' : ''}`}>
                      {snap.supply_change_24h_pct?.toFixed(2)}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="opacity-70">7d 供应变化</span>
                    <span className={`font-mono ${snap.supply_change_7d_pct < 0 ? 'text-red-400' : ''}`}>
                      {snap.supply_change_7d_pct?.toFixed(2)}%
                    </span>
                  </div>
                  {snap.cex_spread_pct > 0 && (
                    <div className="flex justify-between">
                      <span className="opacity-70">CEX 价差</span>
                      <span className="font-mono">{snap.cex_spread_pct?.toFixed(3)}%</span>
                    </div>
                  )}
                  {snap.hard_trigger && (
                    <div className="mt-2 p-2 bg-red-900/50 rounded text-xs">
                      硬触发: {snap.hard_trigger}
                    </div>
                  )}
                  <div className="mt-2 pt-2 border-t border-white/10 flex justify-between">
                    <span className="opacity-50 text-xs">采集时间</span>
                    <span className="text-xs opacity-50 font-mono">
                      {snap.updated_at ? new Date(snap.updated_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '-'}
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-sm opacity-50">暂无数据，等待首次采集</p>
              )}
            </div>
          );
        })}
      </div>

      {/* DEX Liquidity Pools */}
      <div className="bg-gray-900 rounded-lg p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">DEX 流动性</h2>
          <button onClick={() => api.stablecoins.dexPools().then(setDexPools).catch(() => {})}
            className="text-xs text-gray-400 hover:text-gray-200">刷新</button>
        </div>
        {dexPools.length > 0 ? (
          <div className="space-y-3">
            {dexPools.map((p, i) => {
              const slipColor = (v: number) => v > 1 ? 'text-red-400' : v > 0.5 ? 'text-yellow-400' : 'text-green-400';
              return (
                <div key={i} className="bg-gray-800 rounded p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="font-medium text-sm">{p.pool_name}</span>
                      <span className="text-xs text-gray-500 ml-2">{p.dex}</span>
                    </div>
                    <span className="text-xs text-gray-500 font-mono">
                      TVL ${(Number(p.reserve_usd) / 1e6).toFixed(1)}M
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-xs">
                    <div>
                      <span className="text-gray-500 block">价格比</span>
                      <span className="font-mono">{p.price_ratio?.toFixed(5)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500 block">24h 交易量</span>
                      <span className="font-mono">${(Number(p.volume_24h_usd) / 1e6).toFixed(1)}M</span>
                    </div>
                    <div>
                      <span className="text-gray-500 block">1h 交易量</span>
                      <span className="font-mono">${(Number(p.volume_1h_usd) / 1e3).toFixed(0)}K</span>
                    </div>
                  </div>
                  <div className="mt-2 pt-2 border-t border-gray-700 grid grid-cols-3 gap-3 text-xs">
                    <div>
                      <span className="text-gray-500 block">$100K 滑点</span>
                      <span className={`font-mono ${slipColor(p.estimated_slippage_100k)}`}>
                        {p.estimated_slippage_100k?.toFixed(3)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block">$1M 滑点</span>
                      <span className={`font-mono ${slipColor(p.estimated_slippage_1m)}`}>
                        {p.estimated_slippage_1m?.toFixed(3)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500 block">$5M 滑点</span>
                      <span className={`font-mono ${slipColor(p.estimated_slippage_5m)}`}>
                        {p.estimated_slippage_5m?.toFixed(3)}%
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">加载中...</p>
        )}
      </div>

      {/* Issuer Reserve Monitoring */}
      <div className="bg-gray-900 rounded-lg p-6 mb-6">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold">发行方储备监控</h2>
          <button
            onClick={async () => {
              setFetchingReserves(true); setReserveFetchResult(null);
              try {
                const r = await api.stablecoins.fetchReserves();
                setReserveFetchResult(r);
                setReserves(await api.stablecoins.reserves());
              } catch (e: any) {
                setReserveFetchResult({ success: false, error: e.message });
              } finally { setFetchingReserves(false); }
            }}
            disabled={fetchingReserves}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white px-3 py-1 rounded text-xs"
          >{fetchingReserves ? '抓取中...' : '自动抓取'}</button>
        </div>
        <p className="text-gray-500 text-xs mb-4">
          自动从 Circle API 和 Tether API 获取最新数据。也可展开手动录入。
          <a href="https://www.circle.com/transparency" target="_blank" className="text-blue-400 ml-1">Circle</a>
          <a href="https://tether.to/en/transparency/" target="_blank" className="text-blue-400 ml-1">Tether</a>
        </p>
        {reserveFetchResult && (
          <div className={`rounded p-3 text-xs mb-4 ${reserveFetchResult.success ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
            {reserveFetchResult.success ? (
              <div className="space-y-1">
                <div className="font-semibold">抓取成功</div>
                {reserveFetchResult.fetched?.USDT && (
                  <div>USDT: 总资产 ${(reserveFetchResult.fetched.USDT.total_assets / 1e9).toFixed(1)}B | 覆盖率 {(reserveFetchResult.fetched.USDT.coverage_ratio * 100).toFixed(1)}% | {reserveFetchResult.fetched.USDT.chains}链</div>
                )}
                {reserveFetchResult.fetched?.USDC && (
                  <div>USDC: 供应/储备 ${(reserveFetchResult.fetched.USDC.total_supply / 1e9).toFixed(1)}B | {reserveFetchResult.fetched.USDC.chains}链 (Circle 1:1 足额储备)</div>
                )}
              </div>
            ) : `抓取失败: ${reserveFetchResult.error}`}
          </div>
        )}
        <div className="space-y-4">
          {reserves.map(r => {
            const riskColors: Record<string, string> = {
              safe: 'border-green-800', watch: 'border-yellow-800', warning: 'border-orange-800',
              danger: 'border-red-800', critical: 'border-red-600', unknown: 'border-gray-700',
            };
            const riskLabels: Record<string, string> = {
              safe: '安全', watch: '关注', warning: '预警', danger: '危险', critical: '严重', unknown: '未录入',
            };
            return (
              <div key={r.token} className={`bg-gray-800 rounded-lg p-4 border ${riskColors[r.risk_level] || 'border-gray-700'}`}>
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <span className="font-semibold">{r.token}</span>
                    <span className="text-xs text-gray-500 ml-2">{r.issuer}</span>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded ${r.risk_level === 'safe' ? 'bg-green-900 text-green-300' : r.risk_level === 'unknown' ? 'bg-gray-700 text-gray-400' : 'bg-red-900 text-red-300'}`}>
                    {riskLabels[r.risk_level]}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm mb-3">
                  <div className="flex justify-between">
                    <span className="text-gray-500">储备覆盖率</span>
                    <span className={`font-mono ${r.coverage_ratio < 1 ? 'text-red-400' : 'text-green-400'}`}>
                      {r.coverage_ratio > 0 ? `${(r.coverage_ratio * 100).toFixed(1)}%` : '-'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">储备总额</span>
                    <span className="font-mono">
                      {Number(r.total_reserves) > 0 ? `$${(Number(r.total_reserves) / 1e9).toFixed(1)}B` : '-'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">审计报告日期</span>
                    <span className={`font-mono ${r.is_overdue ? 'text-red-400' : ''}`}>
                      {r.report_date !== '未录入' ? r.report_date : '未录入'}
                      {r.is_overdue && r.days_since_report < 999 && ` (${r.days_since_report}天, 逾期)`}
                      {!r.is_overdue && r.days_since_report < 999 && ` (${r.days_since_report}天)`}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">数据抓取</span>
                    <span className="font-mono text-gray-400">
                      {r.last_fetched || '-'}
                    </span>
                  </div>
                </div>

                {Object.keys(r.composition || {}).length > 0 && (
                  <div className="mb-3">
                    <span className="text-xs text-gray-500 block mb-1">储备构成</span>
                    <div className="flex gap-1">
                      {Object.entries(r.composition).map(([k, v]) => (
                        <div key={k} className="bg-gray-700 rounded px-2 py-0.5 text-xs">
                          {k} {v as number}%
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <details className="mt-2">
                  <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-200">更新储备数据</summary>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-gray-500 block">报告日期</label>
                      <input type="date" defaultValue={r.report_date !== '未录入' ? r.report_date : ''}
                        onChange={async e => {
                          await api.stablecoins.updateReserves(r.token, { report_date: e.target.value });
                          setReserves(await api.stablecoins.reserves());
                        }}
                        className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs w-full" />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block">储备总额 (USD)</label>
                      <input type="number" defaultValue={Number(r.total_reserves) || ''}
                        placeholder="例: 76000000000"
                        onBlur={async e => {
                          if (e.target.value) {
                            await api.stablecoins.updateReserves(r.token, { total_reserves: Number(e.target.value) });
                            setReserves(await api.stablecoins.reserves());
                          }
                        }}
                        className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs w-full font-mono" />
                    </div>
                  </div>
                </details>
              </div>
            );
          })}
        </div>
      </div>

      {/* Stablecoin-specific Thresholds */}
      <div className="bg-gray-900 rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">脱锚告警阈值</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">预警偏离 (WARNING)</label>
            <div className="flex items-center gap-2">
              <input type="number" step="0.001" value={riskConfig.depeg_warning || 0.005}
                onChange={e => updateRisk('depeg_warning', Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-28 font-mono" />
              <span className="text-xs text-gray-500">({((riskConfig.depeg_warning || 0.005) * 100).toFixed(1)}%)</span>
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">严重偏离 (CRITICAL)</label>
            <div className="flex items-center gap-2">
              <input type="number" step="0.001" value={riskConfig.depeg_critical || 0.02}
                onChange={e => updateRisk('depeg_critical', Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-28 font-mono" />
              <span className="text-xs text-gray-500">({((riskConfig.depeg_critical || 0.02) * 100).toFixed(1)}%)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Collection Intervals */}
      <div className="bg-gray-900 rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">采集频率</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">价格采集间隔</label>
            <div className="flex items-center gap-2">
              <input type="number" value={intervals.stablecoin_price || 60}
                onChange={e => updateInterval('stablecoin_price', Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-24 font-mono" />
              <span className="text-xs text-gray-500">秒</span>
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">供应量采集间隔</label>
            <div className="flex items-center gap-2">
              <input type="number" value={intervals.stablecoin_supply || 600}
                onChange={e => updateInterval('stablecoin_supply', Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-24 font-mono" />
              <span className="text-xs text-gray-500">秒</span>
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">DEX 流动性刷新</label>
            <select value={reportConfig.dex_liquidity_interval || 300}
              onChange={async e => { setReportConfig(await api.stablecoins.updateReportConfig({ dex_liquidity_interval: Number(e.target.value) })); }}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-full">
              <option value={60}>1 分钟</option>
              <option value={300}>5 分钟</option>
              <option value={600}>10 分钟</option>
              <option value={1800}>30 分钟</option>
              <option value={3600}>1 小时</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">储备自动抓取</label>
            <select value={reportConfig.reserves_fetch_interval || 21600}
              onChange={async e => { setReportConfig(await api.stablecoins.updateReportConfig({ reserves_fetch_interval: Number(e.target.value) })); }}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-full">
              <option value={3600}>1 小时</option>
              <option value={7200}>2 小时</option>
              <option value={14400}>4 小时</option>
              <option value={21600}>6 小时</option>
              <option value={43200}>12 小时</option>
              <option value={86400}>24 小时</option>
            </select>
          </div>
        </div>
      </div>

      {/* Report Push Config */}
      <div className="bg-gray-900 rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold mb-2">定时报告推送</h2>
        <p className="text-gray-500 text-sm mb-4">定时将 USDC/USDT 状态摘要推送到 Telegram</p>

        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={reportConfig.enabled}
                onChange={async e => {
                  const enabled = e.target.checked;
                  const r = await api.stablecoins.updateReportConfig({ enabled });
                  setReportConfig(r);
                }}
                className="w-4 h-4 rounded bg-gray-800 border-gray-600" />
              <span className="text-sm">启用定时推送</span>
            </label>
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-400">推送间隔</label>
              <select value={reportConfig.interval}
                onChange={async e => { setReportConfig(await api.stablecoins.updateReportConfig({ interval: Number(e.target.value) })); }}
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
                  const r = await api.stablecoins.sendReport();
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
                {reportResult.success ? '已发送（含 DEX + 储备数据）' : `失败: ${reportResult.error}`}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Monitoring Layers */}
      <div className="bg-gray-900 rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">监控层级</h2>
        <div className="space-y-2 text-sm">
          {[
            { layer: 1, name: '价格脱锚检测', source: 'CoinGecko + DefiLlama', status: true },
            { layer: 2, name: 'DEX 流动性 / 池倾斜', source: 'GeckoTerminal', status: true },
            { layer: 3, name: '链上供应量与赎回', source: 'DefiLlama', status: true },
            { layer: 4, name: '发行方储备监控', source: 'Circle API + Tether API', status: true },
            { layer: 5, name: '冻结与黑名单', source: '链上 eth_call', status: true },
            { layer: 6, name: '跨链版本校验', source: '白名单', status: true },
            { layer: 7, name: 'CEX 交易所价差', source: 'CoinGecko', status: true },
            { layer: 8, name: '存款协议敞口', source: '协议采集器', status: true },
          ].map(l => (
            <div key={l.layer} className="flex items-center gap-3 py-1">
              <span className={`w-2 h-2 rounded-full ${l.status ? 'bg-green-500' : 'bg-gray-600'}`} />
              <span className="text-gray-400 w-6">L{l.layer}</span>
              <span className="flex-1">{l.name}</span>
              <span className="text-xs text-gray-600">{l.source}</span>
              <span className={`text-xs ${l.status ? 'text-green-500' : 'text-gray-600'}`}>
                {l.status ? '已启用' : '待实现'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Depeg Action Reference */}
      <div className="bg-gray-900 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-4">脱锚操作参考</h2>
        <div className="space-y-1">
          {DEPEG_THRESHOLDS.map((t, i) => (
            <div key={i} className="flex items-center gap-3 text-sm py-1">
              <span className="font-mono w-32 text-gray-400">{t.range}</span>
              <span className={`w-16 ${t.color}`}>{t.status}</span>
              <span className="text-gray-500">{t.action}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
