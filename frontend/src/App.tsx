import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Dashboard } from './pages/Dashboard';
import { Settings } from './pages/Settings';
import { Protocols } from './pages/Protocols';
import { Stablecoins } from './pages/Stablecoins';
import { Notifications } from './pages/Notifications';

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="border-b border-gray-800">
        <div className="max-w-6xl mx-auto px-6 py-3 flex gap-6 items-center">
          <span className="text-lg font-bold text-white">Stake Watch</span>
          <NavLink to="/" className={({ isActive }) =>
            isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
          }>仪表盘</NavLink>
          <NavLink to="/protocols" className={({ isActive }) =>
            isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
          }>质押协议</NavLink>
          <NavLink to="/stablecoins" className={({ isActive }) =>
            isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
          }>稳定币监控</NavLink>
          <NavLink to="/notifications" className={({ isActive }) =>
            isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
          }>推送配置</NavLink>
          <NavLink to="/settings" className={({ isActive }) =>
            isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
          }>设置</NavLink>
        </div>
      </nav>
      <main className="max-w-6xl mx-auto p-6">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/protocols" element={<Protocols />} />
          <Route path="/stablecoins" element={<Stablecoins />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
