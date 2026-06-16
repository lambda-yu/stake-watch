import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { WalletForm } from '../components/WalletForm';

const INTERVAL_LABELS: Record<string, string> = {
  positions: '仓位采集',
  protocol_stats: '协议统计',
  reserves: '储备报告',
};

const INTERVAL_HIDDEN = new Set(['stablecoin_price', 'stablecoin_supply']);

const RISK_LABELS: Record<string, string> = {
  liquidation_warning: '清算预警阈值',
  liquidation_critical: '清算严重阈值',
  tvl_crash_threshold: 'TVL 暴跌阈值',
  apy_change_threshold: 'APY 波动阈值',
};

const RISK_HIDDEN = new Set(['depeg_warning', 'depeg_critical']);

export function Settings() {
  const [wallets, setWallets] = useState<any[]>([]);
  const [intervals, setIntervals] = useState<any>({});
  const [risk, setRisk] = useState<any>({});
  const [tzOffset, setTzOffset] = useState(8);

  const reload = async () => {
    try {
      setWallets(await api.wallets.list());
      setIntervals(await api.intervals.get());
      setRisk(await api.risk.get());
      const tz = await api.timezone.get();
      setTzOffset(tz.offset);
    } catch {}
  };
  useEffect(() => { reload(); }, []);

  const addWallet = async (data: any) => { await api.wallets.add(data); reload(); };
  const deleteWallet = async (id: number) => { await api.wallets.delete(id); reload(); };
  const updateInterval = async (key: string, value: number) => { await api.intervals.update({ [key]: value }); reload(); };
  const updateRisk = async (key: string, value: number) => { await api.risk.update({ [key]: value }); reload(); };

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <section>
        <h2 className="text-xl font-semibold mb-3">时区设置</h2>
        <p className="text-gray-600 text-xs mb-3">影响 Telegram 推送消息中的时间显示</p>
        <div className="flex items-center gap-3">
          <select value={tzOffset}
            onChange={async e => {
              const v = Number(e.target.value);
              setTzOffset(v);
              await api.timezone.update(v);
            }}
            className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm">
            <option value={-12}>UTC-12</option>
            <option value={-11}>UTC-11</option>
            <option value={-10}>UTC-10 (Hawaii)</option>
            <option value={-9}>UTC-9 (Alaska)</option>
            <option value={-8}>UTC-8 (太平洋)</option>
            <option value={-7}>UTC-7 (山地)</option>
            <option value={-6}>UTC-6 (中部)</option>
            <option value={-5}>UTC-5 (东部)</option>
            <option value={-4}>UTC-4</option>
            <option value={-3}>UTC-3</option>
            <option value={0}>UTC+0 (伦敦)</option>
            <option value={1}>UTC+1 (中欧)</option>
            <option value={2}>UTC+2 (东欧)</option>
            <option value={3}>UTC+3 (莫斯科)</option>
            <option value={4}>UTC+4 (迪拜)</option>
            <option value={5}>UTC+5</option>
            <option value={5.5}>UTC+5:30 (印度)</option>
            <option value={6}>UTC+6</option>
            <option value={7}>UTC+7 (曼谷)</option>
            <option value={8}>UTC+8 (北京/新加坡)</option>
            <option value={9}>UTC+9 (东京/首尔)</option>
            <option value={10}>UTC+10 (悉尼)</option>
            <option value={12}>UTC+12 (奥克兰)</option>
          </select>
          <span className="text-sm text-gray-500">当前: UTC{tzOffset >= 0 ? '+' : ''}{tzOffset}</span>
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">钱包管理</h2>
        <WalletForm onAdd={addWallet} />
        <div className="mt-3 space-y-2">
          {wallets.map(w => (
            <div key={w.id} className="flex items-center justify-between bg-gray-900 rounded p-3">
              <div>
                <span className="text-xs bg-gray-700 px-2 py-0.5 rounded mr-2">{w.chain}</span>
                <span className="font-mono text-sm">{w.address}</span>
                {w.label && <span className="text-gray-500 ml-2 text-sm">{w.label}</span>}
              </div>
              <button onClick={() => deleteWallet(w.id)} className="text-red-400 hover:text-red-300 text-sm">删除</button>
            </div>
          ))}
          {wallets.length === 0 && <p className="text-gray-500 text-sm">暂未配置钱包</p>}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">采集间隔 (秒)</h2>
        <p className="text-gray-600 text-xs mb-3">稳定币采集频率请在「稳定币监控」页面配置</p>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(intervals).filter(([key]) => !INTERVAL_HIDDEN.has(key)).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-sm text-gray-400 w-40">{INTERVAL_LABELS[key] || key}</label>
              <input type="number" value={val as number}
                onChange={e => updateInterval(key, Number(e.target.value))}
                className="bg-gray-800 border border-gray-700 rounded px-3 py-1 text-sm w-24" />
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold mb-3">风险阈值</h2>
        <p className="text-gray-600 text-xs mb-3">脱锚阈值请在「稳定币监控」页面配置</p>
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(risk).filter(([key]) => !RISK_HIDDEN.has(key)).map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-sm text-gray-400 w-48">{RISK_LABELS[key] || key}</label>
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
