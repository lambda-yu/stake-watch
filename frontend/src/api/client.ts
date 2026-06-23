const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (resp.status === 204) return undefined as T;
  if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
  return resp.json();
}

export const api = {
  wallets: {
    list: () => request<any[]>('/config/wallets'),
    add: (data: { chain: string; address: string; label?: string }) =>
      request<any>('/config/wallets', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id: number) =>
      request<void>(`/config/wallets/${id}`, { method: 'DELETE' }),
  },
  protocols: {
    list: () => request<any[]>('/protocols'),
    add: (data: any) =>
      request<any>('/protocols', { method: 'POST', body: JSON.stringify(data) }),
    toggle: (id: number) =>
      request<any>(`/protocols/${id}/toggle`, { method: 'PATCH' }),
    delete: (id: number) =>
      request<void>(`/protocols/${id}`, { method: 'DELETE' }),
    refresh: () => request<any>('/protocols/refresh', { method: 'POST' }),
    evaluate: (id: number) => request<any>(`/protocols/${id}/evaluate`, { method: 'POST' }),
    riskStatus: (id: number, refresh = false) =>
      request<any>(`/protocols/${id}/risk-status${refresh ? '?refresh=true' : ''}`),
    reportConfig: () => request<any>('/protocols/report-config'),
    updateReportConfig: (data: { interval?: number; enabled?: boolean }) =>
      request<any>('/protocols/report-config', { method: 'PUT', body: JSON.stringify(data) }),
    sendReport: () => request<any>('/protocols/report/send', { method: 'POST' }),
  },
  intervals: {
    get: () => request<any>('/config/intervals'),
    update: (data: any) =>
      request<any>('/config/intervals', { method: 'PUT', body: JSON.stringify(data) }),
  },
  risk: {
    get: () => request<any>('/config/risk'),
    update: (data: any) =>
      request<any>('/config/risk', { method: 'PUT', body: JSON.stringify(data) }),
  },
  timezone: {
    get: () => request<any>('/config/timezone'),
    update: (offset: number) =>
      request<any>('/config/timezone', { method: 'PUT', body: JSON.stringify({ offset }) }),
  },
  telegram: {
    get: () => request<any>('/config/telegram'),
    update: (data: { bot_token?: string; chat_id?: string }) =>
      request<any>('/config/telegram', { method: 'PUT', body: JSON.stringify(data) }),
    test: () => request<any>('/config/telegram/test', { method: 'POST' }),
    testSample: (key: string) =>
      request<any>(`/config/telegram/test/${key}`, { method: 'POST' }),
    samples: () => request<any[]>('/config/telegram/samples'),
    bindStart: () => request<any>('/config/telegram/bind/start', { method: 'POST' }),
    bindStatus: () => request<any>('/config/telegram/bind/status'),
    bindCancel: () => request<any>('/config/telegram/bind/cancel', { method: 'POST' }),
  },
  status: {
    get: () => request<any>('/status'),
  },
  comparison: {
    get: () => request<{ rows: any[]; count: number }>('/comparison'),
  },
  stablecoins: {
    snapshots: () => request<any[]>('/stablecoins'),
    dexPools: () => request<any[]>('/stablecoins/dex-pools'),
    reserves: () => request<any[]>('/stablecoins/reserves'),
    updateReserves: (token: string, data: any) =>
      request<any>(`/stablecoins/reserves/${token}`, { method: 'PUT', body: JSON.stringify(data) }),
    fetchReserves: () => request<any>('/stablecoins/reserves/fetch', { method: 'POST' }),
    reportConfig: () => request<any>('/stablecoins/report-config'),
    updateReportConfig: (data: { interval?: number; enabled?: boolean }) =>
      request<any>('/stablecoins/report-config', { method: 'PUT', body: JSON.stringify(data) }),
    sendReport: () => request<any>('/stablecoins/report/send', { method: 'POST' }),
    collect: () => request<any>('/stablecoins/collect', { method: 'POST' }),
  },
};
