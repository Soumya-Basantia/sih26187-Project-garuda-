import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { ThemeProvider } from './hooks/useTheme'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import CameraManagement from './pages/CameraManagement'
import ZoneEditor from './pages/ZoneEditor'
import Identities from './pages/Identities'
import EventHistory from './pages/EventHistory'
import Analytics from './pages/Analytics'
import SystemHealth from './pages/SystemHealth'
import Settings from './pages/Settings'
import AuthorizationManagement from './pages/AuthorizationManagement'
import Attendance from './pages/Attendance'
import TacticalRadarPage from './pages/TacticalRadarPage'
import AILearningLab from './pages/AILearningLab'
import BlockchainVault from './pages/BlockchainVault'
import CyberSecurityHub from './pages/CyberSecurityHub'
import Layout from './components/Layout'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/tactical-map" element={<TacticalRadarPage />} />
                <Route path="/cameras" element={<CameraManagement />} />
                <Route path="/zones" element={<ZoneEditor />} />
                <Route path="/identities" element={<Identities />} />
                <Route path="/authorization" element={<AuthorizationManagement />} />
                <Route path="/attendance" element={<Attendance />} />
                <Route path="/blockchain" element={<BlockchainVault />} />
                <Route path="/cybersecurity" element={<CyberSecurityHub />} />
                <Route path="/learning-lab" element={<AILearningLab />} />
                <Route path="/history" element={<EventHistory />} />
                <Route path="/analytics" element={<Analytics />} />
                <Route path="/system-health" element={<SystemHealth />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </ThemeProvider>
  )
}
