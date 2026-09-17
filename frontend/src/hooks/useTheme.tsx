import React, { createContext, useContext, useEffect, useState } from 'react'

export type ThemeMode = 'dark' | 'light' | 'system'

interface ThemeContextType {
  theme: ThemeMode
  resolvedTheme: 'dark' | 'light'
  setTheme: (mode: ThemeMode) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

const THEME_STORAGE_KEY = 'garuda_theme_preference'

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode | null
    if (saved === 'dark' || saved === 'light' || saved === 'system') {
      return saved
    }
    return 'dark' // Default to Tactical Dark for defense command center
  })

  const [resolvedTheme, setResolvedTheme] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    const root = document.documentElement
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    function applyTheme() {
      let isDark = true
      if (theme === 'system') {
        isDark = mediaQuery.matches
      } else {
        isDark = theme === 'dark'
      }

      setResolvedTheme(isDark ? 'dark' : 'light')

      if (isDark) {
        root.classList.add('dark')
        root.classList.remove('light')
        root.style.colorScheme = 'dark'
      } else {
        root.classList.remove('dark')
        root.classList.add('light')
        root.style.colorScheme = 'light'
      }
    }

    applyTheme()
    localStorage.setItem(THEME_STORAGE_KEY, theme)

    const handler = () => {
      if (theme === 'system') applyTheme()
    }
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [theme])

  function setTheme(mode: ThemeMode) {
    setThemeState(mode)
  }

  function toggleTheme() {
    setThemeState((prev) => {
      const current = prev === 'system' ? resolvedTheme : prev
      return current === 'dark' ? 'light' : 'dark'
    })
  }

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
