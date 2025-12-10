'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Server, Loader2, RefreshCw, Terminal, ArrowLeft, AlertCircle } from 'lucide-react'

interface Container {
  id: string
  name: string
  image: string
  status: string
  created: string
}

export default function AdminPage() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [containers, setContainers] = useState<Container[]>([])
  const [selectedContainer, setSelectedContainer] = useState<string | null>(null)
  const [logs, setLogs] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})

  // Dummy credentials
  const ADMIN_USERNAME = 'admin'
  const ADMIN_PASSWORD = 'admin123'

  useEffect(() => {
    // Check if already authenticated
    const authStatus = sessionStorage.getItem('adminAuth')
    if (authStatus === 'true') {
      setIsAuthenticated(true)
      loadContainers()
    }
  }, [])

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (username === ADMIN_USERNAME && password === ADMIN_PASSWORD) {
      setIsAuthenticated(true)
      sessionStorage.setItem('adminAuth', 'true')
      loadContainers()
    } else {
      setError('Invalid username or password')
    }
  }

  const handleLogout = () => {
    setIsAuthenticated(false)
    sessionStorage.removeItem('adminAuth')
    setUsername('')
    setPassword('')
    setContainers([])
    setLogs({})
  }

  const loadContainers = async () => {
    // Fetch container list from Docker API
    try {
      const response = await fetch('/api/admin/containers')
      if (response.ok) {
        const data = await response.json()
        setContainers(data)
      }
    } catch (error) {
      console.error('Failed to load containers:', error)
    }
  }

  const fetchLogs = async (containerId: string, containerName: string) => {
    setLoading({ ...loading, [containerId]: true })
    try {
      const response = await fetch(`/api/admin/logs/${containerId}`)
      if (response.ok) {
        const data = await response.json()
        setLogs({ ...logs, [containerId]: data.logs })
      }
    } catch (error) {
      console.error(`Failed to fetch logs for ${containerName}:`, error)
      setLogs({ ...logs, [containerId]: 'Error loading logs' })
    } finally {
      setLoading({ ...loading, [containerId]: false })
    }
  }

  const handleRefreshLogs = () => {
    if (selectedContainer) {
      const container = containers.find(c => c.id === selectedContainer)
      if (container) {
        fetchLogs(container.id, container.name)
      }
    }
  }

  const handleSelectContainer = (containerId: string) => {
    setSelectedContainer(containerId)
    const container = containers.find(c => c.id === containerId)
    if (container && !logs[containerId]) {
      fetchLogs(containerId, container.name)
    }
  }

  // Login form
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-gray-100">
        <div className="max-w-md w-full mx-4">
          <div className="bg-white rounded-2xl shadow-2xl p-8 border border-gray-100">
            <div className="text-center mb-8">
              <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-primary-500 to-primary-600 rounded-2xl mb-4 shadow-lg">
                <Server className="w-10 h-10 text-white" />
              </div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">Admin Panel</h1>
              <p className="text-sm text-gray-600">Docker Container Logs Management</p>
            </div>

            <form onSubmit={handleLogin} className="space-y-5">
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all outline-none text-gray-900"
                  placeholder="Enter username"
                  required
                  autoComplete="username"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-all outline-none text-gray-900"
                  placeholder="Enter password"
                  required
                  autoComplete="current-password"
                />
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm font-medium flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="w-full bg-gradient-to-r from-primary-600 to-primary-700 text-white py-3 rounded-xl hover:from-primary-700 hover:to-primary-800 transition-all font-semibold shadow-lg hover:shadow-xl transform hover:-translate-y-0.5"
              >
                Login to Admin Panel
              </button>
{/* 
              <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 mt-4">
                <p className="text-xs font-semibold text-gray-600 mb-1">Demo Credentials:</p>
                <p className="text-sm text-gray-800 font-mono">
                  <span className="font-semibold">Username:</span> admin<br />
                  <span className="font-semibold">Password:</span> admin123
                </p>
              </div> */}
            </form>
          </div>
        </div>
      </div>
    )
  }

  // Admin dashboard
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
              <p className="text-sm text-gray-500 mt-1">Docker Container Logs</p>
            </div>
            <div className="flex gap-3">
              <Link
                href="/"
                className="inline-flex items-center gap-2 px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                Dashboard
              </Link>
              <button
                onClick={loadContainers}
                className="inline-flex items-center gap-2 px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh
              </button>
              <button
                onClick={handleLogout}
                className="px-4 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Containers List */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200">
              <div className="p-4 border-b bg-gradient-to-r from-gray-50 to-white">
                <h2 className="font-bold text-gray-900 flex items-center gap-2">
                  <Server className="w-5 h-5 text-primary-600" />
                  Containers
                </h2>
                <p className="text-xs text-gray-600 mt-1">{containers.length} active</p>
              </div>
              <div className="divide-y max-h-[calc(100vh-250px)] overflow-y-auto">
                {containers.length === 0 ? (
                  <div className="p-12 text-center text-gray-500">
                    <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 rounded-full flex items-center justify-center">
                      <Server className="w-8 h-8 text-gray-400" />
                    </div>
                    <p className="font-medium text-gray-700">No containers found</p>
                    <p className="text-xs mt-1">Make sure Docker is running</p>
                  </div>
                ) : (
                  containers.map((container) => (
                    <div
                      key={container.id}
                      className={`p-4 cursor-pointer transition-all duration-200 ${
                        selectedContainer === container.id
                          ? 'bg-gradient-to-r from-primary-50 to-primary-100 border-l-4 border-primary-600 shadow-inner'
                          : 'hover:bg-gray-50 border-l-4 border-transparent'
                      }`}
                      onClick={() => handleSelectContainer(container.id)}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`p-2 rounded-lg ${
                          selectedContainer === container.id ? 'bg-primary-200' : 'bg-gray-100'
                        }`}>
                          <Terminal className={`w-4 h-4 ${
                            selectedContainer === container.id ? 'text-primary-700' : 'text-gray-600'
                          }`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="font-semibold text-gray-900 truncate text-sm">{container.name}</h3>
                          <p className="text-xs text-gray-600 mt-1 truncate font-mono">{container.image}</p>
                          <div className="mt-2 flex items-center gap-2">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                              container.status === 'running'
                                ? 'bg-green-100 text-green-800'
                                : 'bg-gray-100 text-gray-800'
                            }`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${
                                container.status === 'running' ? 'bg-green-500' : 'bg-gray-500'
                              }`}></span>
                              {container.status}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Logs Display */}
          <div className="lg:col-span-3">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
              {selectedContainer ? (
                <>
                  <div className="p-4 border-b bg-gradient-to-r from-gray-50 to-white flex justify-between items-center">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-primary-100 rounded-lg">
                        <Terminal className="w-5 h-5 text-primary-600" />
                      </div>
                      <div>
                        <h2 className="font-bold text-gray-900">
                          {containers.find(c => c.id === selectedContainer)?.name || 'Container Logs'}
                        </h2>
                        <p className="text-xs text-gray-600 mt-0.5 font-mono">
                          {containers.find(c => c.id === selectedContainer)?.image}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={handleRefreshLogs}
                      disabled={loading[selectedContainer]}
                      className="inline-flex items-center gap-2 px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
                    >
                      <RefreshCw className={`w-4 h-4 ${loading[selectedContainer] ? 'animate-spin' : ''}`} />
                      Refresh Logs
                    </button>
                  </div>
                  <div className="p-4 bg-gray-50">
                    <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-xl p-5 shadow-inner border border-gray-700 max-h-[calc(100vh-300px)] overflow-y-auto">
                      {loading[selectedContainer] ? (
                        <div className="flex flex-col items-center justify-center py-16">
                          <Loader2 className="w-8 h-8 animate-spin text-primary-400 mb-3" />
                          <p className="text-gray-400 text-sm">Loading logs...</p>
                        </div>
                      ) : (
                        <pre className="text-xs text-green-400 font-mono whitespace-pre-wrap leading-relaxed">
                          {logs[selectedContainer] || (
                            <span className="text-gray-500">No logs available for this container</span>
                          )}
                        </pre>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="p-16 text-center text-gray-500">
                  <div className="w-20 h-20 mx-auto mb-6 bg-gradient-to-br from-gray-100 to-gray-200 rounded-2xl flex items-center justify-center">
                    <Terminal className="w-10 h-10 text-gray-400" />
                  </div>
                  <p className="text-lg font-semibold text-gray-700 mb-2">Select a Container</p>
                  <p className="text-sm text-gray-500">Choose a container from the list to view its logs</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
