import { useEffect, useState } from 'react';
import { api } from '../api/client';

export function Notifications() {
  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [configured, setConfigured] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; error?: string } | null>(null);
  const [showToken, setShowToken] = useState(false);

  useEffect(() => {
    api.telegram.get().then(data => {
      setBotToken(data.bot_token || '');
      setChatId(data.chat_id || '');
      setConfigured(data.configured);
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      const data = await api.telegram.update({ bot_token: botToken, chat_id: chatId });
      setConfigured(data.configured);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.telegram.test();
      setTestResult(result);
    } catch (e: any) {
      setTestResult({ success: false, error: e.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">推送配置</h1>

      <div className="bg-gray-900 rounded-lg p-6 space-y-6">
        <div className="flex items-center gap-3 pb-4 border-b border-gray-800">
          <div className={`w-3 h-3 rounded-full ${configured ? 'bg-green-500' : 'bg-gray-600'}`} />
          <span className="text-sm">
            {configured ? 'Telegram 已配置' : 'Telegram 未配置'}
          </span>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-4">Telegram Bot</h2>
          <p className="text-gray-500 text-sm mb-4">
            1. 在 Telegram 中搜索 @BotFather，发送 /newbot 创建机器人，获取 Bot Token<br/>
            2. 将机器人添加到群组或直接对话，获取 Chat ID（可通过 @userinfobot 查看）
          </p>

          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Bot Token</label>
              <div className="flex gap-2">
                <input
                  type={showToken ? 'text' : 'password'}
                  value={botToken}
                  onChange={e => setBotToken(e.target.value)}
                  placeholder="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                  className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm flex-1 font-mono"
                />
                <button
                  onClick={() => setShowToken(!showToken)}
                  className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-400 hover:text-gray-200"
                >
                  {showToken ? '隐藏' : '显示'}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Chat ID</label>
              <input
                type="text"
                value={chatId}
                onChange={e => setChatId(e.target.value)}
                placeholder="-1001234567890 或个人 ID"
                className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm w-full font-mono"
              />
            </div>
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:text-gray-400 text-white px-5 py-2 rounded text-sm"
          >
            {saving ? '保存中...' : '保存配置'}
          </button>
          <button
            onClick={handleTest}
            disabled={testing || !configured}
            className="bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-500 text-white px-5 py-2 rounded text-sm"
          >
            {testing ? '发送中...' : '发送测试消息'}
          </button>
        </div>

        {testResult && (
          <div className={`rounded p-3 text-sm ${testResult.success ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
            {testResult.success ? '测试消息发送成功，请检查 Telegram' : `发送失败: ${testResult.error}`}
          </div>
        )}
      </div>

      <div className="mt-6 bg-gray-900 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-3">告警级别说明</h2>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-3">
            <span className="text-red-400 font-mono w-24">CRITICAL</span>
            <span className="text-gray-400">严重告警 — 清算风险、脱锚 &gt;1%、份额价格下降、提现受阻</span>
            <span className="text-gray-600 ml-auto">冷却 15 分钟</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-yellow-400 font-mono w-24">WARNING</span>
            <span className="text-gray-400">预警 — 清算接近、供应量骤降、高利用率</span>
            <span className="text-gray-600 ml-auto">冷却 1 小时</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-blue-400 font-mono w-24">INFO</span>
            <span className="text-gray-400">信息 — APY 波动、治理事件</span>
            <span className="text-gray-600 ml-auto">冷却 6 小时</span>
          </div>
        </div>
      </div>
    </div>
  );
}
