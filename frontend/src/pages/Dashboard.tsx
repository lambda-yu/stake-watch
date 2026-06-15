import { useEffect, useState } from 'react';
import { api } from '../api/client';

export function Dashboard() {
  const [status, setStatus] = useState<any>(null);
  useEffect(() => { api.status.get().then(setStatus).catch(() => {}); }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
      {status ? (
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500"></span>
            <span>System {status.status}</span>
            <span className="text-gray-500 text-sm ml-2">v{status.version}</span>
          </div>
        </div>
      ) : (
        <p className="text-gray-500">Connecting to backend...</p>
      )}
    </div>
  );
}
