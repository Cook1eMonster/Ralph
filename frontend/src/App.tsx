import { Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import NewProject from './pages/NewProject'
import FactoryFloor from './pages/FactoryFloor'

function App() {
  return (
    <div className="min-h-screen bg-gray-900">
      <header className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <h1 className="text-2xl font-bold text-white">
            Ralph <span className="text-gray-400 text-sm font-normal">v2.0</span>
          </h1>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewProject />} />
          <Route path="/project/:projectId" element={<FactoryFloor />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
