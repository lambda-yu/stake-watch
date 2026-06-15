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

  useEffect(() => {
    api.stablecoins.snapshots().then(setSnapshots).catch(() => {});
    api.risk.get().then(setRiskConfig).catch(() => {});
    api.intervals.get().then(setIntervals).catch(() => {});
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
      <h1 className="text-2xl font-bold mb-6">稳定币监控</h1>

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
                </div>
              ) : (
                <p className="text-sm opacity-50">暂无数据，等待首次采集</p>
              )}
            </div>
          );
        })}
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
        </div>
      </div>

      {/* Monitoring Layers */}
      <div className="bg-gray-900 rounded-lg p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">监控层级</h2>
        <div className="space-y-2 text-sm">
          {[
            { layer: 1, name: '价格脱锚检测', source: 'CoinGecko + DefiLlama', status: true },
            { layer: 2, name: 'DEX 流动性 / 池倾斜', source: '链上 DEX', status: false },
            { layer: 3, name: '链上供应量与赎回', source: 'DefiLlama', status: true },
            { layer: 4, name: '发行方储备监控', source: 'Circle / Tether', status: false },
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
