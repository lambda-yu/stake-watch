import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Dashboard } from './pages/Dashboard';
import { Settings } from './pages/Settings';
import { Protocols } from './pages/Protocols';

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="border-b border-gray-800 px-6 py-3 flex gap-6 items-center">
        <span className="text-lg font-bold text-white">Stake Watch</span>
        <NavLink to="/" className={({ isActive }) =>
          isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
        }>Dashboard</NavLink>
        <NavLink to="/settings" className={({ isActive }) =>
          isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
        }>Settings</NavLink>
        <NavLink to="/protocols" className={({ isActive }) =>
          isActive ? 'text-blue-400' : 'text-gray-400 hover:text-gray-200'
        }>Protocols</NavLink>
      </nav>
      <main className="p-6">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/protocols" element={<Protocols />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
