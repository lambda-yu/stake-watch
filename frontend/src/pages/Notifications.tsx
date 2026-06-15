import { useEffect, useState, useRef } from 'react';
import { api } from '../api/client';

export function Notifications() {
  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [configured, setConfigured] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; error?: string } | null>(null);
  const [showToken, setShowToken] = useState(false);

  // Bind state
  const [bindCode, setBindCode] = useState('');
  const [bindStatus, setBindStatus] = useState<'idle' | 'waiting' | 'bound' | 'expired'>('idle');
  const [binding, setBinding] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.telegram.get().then(data => {
      setBotToken(data.bot_token || '');
      setChatId(data.chat_id || '');
      setConfigured(data.configured);
    }).catch(() => {});
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
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

  const handleStartBind = async () => {
    if (!botToken) {
      setTestResult({ success: false, error: '请先填写并保存 Bot Token' });
      return;
    }
    await handleSave();
    setBinding(true);
    setBindStatus('waiting');
    setTestResult(null);
    try {
      const result = await api.telegram.bindStart();
      if (!result.success) {
        setTestResult({ success: false, error: result.error });
        setBinding(false);
        setBindStatus('idle');
        return;
      }
      setBindCode(result.code);
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.telegram.bindStatus();
          if (status.status === 'bound') {
            setChatId(status.chat_id);
            setConfigured(true);
            setBindStatus('bound');
            setBinding(false);
            if (pollRef.current) clearInterval(pollRef.current);
          } else if (status.status === 'expired') {
            setBindStatus('expired');
            setBinding(false);
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {}
      }, 2000);
    } catch (e: any) {
      setTestResult({ success: false, error: e.message });
      setBinding(false);
      setBindStatus('idle');
    }
  };

  const handleCancelBind = async () => {
    if (pollRef.current) clearInterval(pollRef.current);
    await api.telegram.bindCancel().catch(() => {});
    setBinding(false);
    setBindStatus('idle');
    setBindCode('');
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">推送配置</h1>

      <div className="bg-gray-900 rounded-lg p-6 space-y-6">
        <div className="flex items-center gap-3 pb-4 border-b border-gray-800">
          <div className={`w-3 h-3 rounded-full ${configured ? 'bg-green-500' : 'bg-gray-600'}`} />
          <span className="text-sm">
            {configured ? 'Telegram 已绑定' : 'Telegram 未绑定'}
          </span>
          {configured && chatId && (
            <span className="text-xs text-gray-500 font-mono ml-auto">Chat ID: {chatId}</span>
          )}
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-4">Telegram Bot 配置</h2>
          <p className="text-gray-500 text-sm mb-4">
            在 Telegram 中搜索 @BotFather，发送 /newbot 创建机器人，获取 Bot Token
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
              <div className="flex gap-2">
                <input
                  type="text"
                  value={chatId}
                  onChange={e => setChatId(e.target.value)}
                  placeholder="通过下方「监听绑定」自动获取，或手动输入"
                  className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm flex-1 font-mono"
                  readOnly={binding}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="flex gap-3">
          <button onClick={handleSave} disabled={saving}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:text-gray-400 text-white px-5 py-2 rounded text-sm">
            {saving ? '保存中...' : '保存配置'}
          </button>
          <button onClick={handleTest} disabled={testing || !configured}
            className="bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-500 text-white px-5 py-2 rounded text-sm">
            {testing ? '发送中...' : '发送测试'}
          </button>
        </div>

        {testResult && (
          <div className={`rounded p-3 text-sm ${testResult.success ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
            {testResult.success ? '测试消息发送成功，请检查 Telegram' : `失败: ${testResult.error}`}
          </div>
        )}
      </div>

      {/* Bind Section */}
      <div className="mt-6 bg-gray-900 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-3">监听绑定</h2>
        <p className="text-gray-500 text-sm mb-4">
          无需手动查找 Chat ID。点击「开始绑定」生成验证码，将验证码发送给你的 Bot，系统自动识别并绑定。
        </p>

        {bindStatus === 'idle' && (
          <button onClick={handleStartBind} disabled={!botToken}
            className="bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 text-white px-5 py-2 rounded text-sm">
            开始绑定
          </button>
        )}

        {bindStatus === 'waiting' && (
          <div className="space-y-4">
            <div className="bg-gray-800 rounded-lg p-6 text-center">
              <p className="text-gray-400 text-sm mb-3">请在 Telegram 中向你的 Bot 发送以下验证码：</p>
              <div className="text-4xl font-mono font-bold tracking-[0.3em] text-white mb-3">
                {bindCode}
              </div>
              <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
                <span className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
                等待验证中... (5 分钟内有效)
              </div>
            </div>
            <div className="bg-gray-800/50 rounded p-3 text-xs text-gray-500 space-y-1">
              <p>1. 打开 Telegram，找到你创建的 Bot</p>
              <p>2. 发送消息：<span className="font-mono text-gray-300">{bindCode}</span></p>
              <p>3. 系统会自动识别并完成绑定</p>
              <p className="text-gray-600">提示：可以在私聊或群组中发送，绑定的是发送消息所在的聊天</p>
            </div>
            <button onClick={handleCancelBind}
              className="text-gray-400 hover:text-gray-200 text-sm">
              取消绑定
            </button>
          </div>
        )}

        {bindStatus === 'bound' && (
          <div className="bg-green-900/50 rounded p-4 text-sm text-green-300 space-y-1">
            <p className="font-semibold">绑定成功</p>
            <p>Chat ID: <span className="font-mono">{chatId}</span></p>
            <button onClick={() => setBindStatus('idle')} className="text-green-400 hover:text-green-200 text-xs mt-2">
              确定
            </button>
          </div>
        )}

        {bindStatus === 'expired' && (
          <div className="bg-yellow-900/50 rounded p-4 text-sm text-yellow-300 space-y-2">
            <p>验证码已过期</p>
            <button onClick={() => { setBindStatus('idle'); setBindCode(''); }}
              className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-1 rounded text-sm">
              重新绑定
            </button>
          </div>
        )}
      </div>

      {/* Alert Level Reference */}
      <div className="mt-6 bg-gray-900 rounded-lg p-6">
        <h2 className="text-lg font-semibold mb-3">告警级别说明</h2>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-3">
            <span className="text-red-400 font-mono w-24">CRITICAL</span>
            <span className="text-gray-400">严重 — 清算风险、脱锚 &gt;1%、份额价格下降、提现受阻</span>
            <span className="text-gray-600 ml-auto">15 分钟</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-yellow-400 font-mono w-24">WARNING</span>
            <span className="text-gray-400">预警 — 清算接近、供应量骤降、高利用率</span>
            <span className="text-gray-600 ml-auto">1 小时</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-blue-400 font-mono w-24">INFO</span>
            <span className="text-gray-400">信息 — APY 波动、治理事件</span>
            <span className="text-gray-600 ml-auto">6 小时</span>
          </div>
        </div>
      </div>
    </div>
  );
}
