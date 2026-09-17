import React, { createContext, useContext, useState } from 'react'
import { authApi } from '../services/api'

interface AuthState {
  token: string | null
  role: string | null
  username: string | null
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Use sessionStorage so every fresh program launch / new browser session requires security login
  const [token, setToken] = useState<string | null>(() => {
    // Purge old persistent tokens from localStorage so old sessions don't bypass security login
    if (localStorage.getItem('garude_token') && !sessionStorage.getItem('garude_token')) {
      localStorage.removeItem('garude_token')
      localStorage.removeItem('garude_role')
      localStorage.removeItem('garude_username')
    }
    return sessionStorage.getItem('garude_token')
  })
  const [role, setRole] = useState<string | null>(() => sessionStorage.getItem('garude_role'))
  const [username, setUsername] = useState<string | null>(() => sessionStorage.getItem('garude_username'))

  async function login(user: string, password: string, rememberMe: boolean = false) {
    const res = await authApi.login(user, password)
    const access_token = res.data.access_token
    const userRole = res.data.role

    // Always store in sessionStorage for current tab session
    sessionStorage.setItem('garude_token', access_token)
    sessionStorage.setItem('garude_role', userRole)
    sessionStorage.setItem('garude_username', user)

    if (rememberMe) {
      localStorage.setItem('garude_token', access_token)
      localStorage.setItem('garude_role', userRole)
      localStorage.setItem('garude_username', user)
    } else {
      localStorage.removeItem('garude_token')
      localStorage.removeItem('garude_role')
      localStorage.removeItem('garude_username')
    }

    setToken(access_token)
    setRole(userRole)
    setUsername(user)
  }

  function logout() {
    sessionStorage.removeItem('garude_token')
    sessionStorage.removeItem('garude_role')
    sessionStorage.removeItem('garude_username')
    localStorage.removeItem('garude_token')
    localStorage.removeItem('garude_role')
    localStorage.removeItem('garude_username')
    setToken(null)
    setRole(null)
    setUsername(null)
  }

  return (
    <AuthContext.Provider value={{ token, role, username, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
