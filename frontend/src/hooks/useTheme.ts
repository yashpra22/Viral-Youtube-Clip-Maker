import { useCallback, useEffect, useState } from 'react'

type Theme = 'light' | 'dark'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>('light')

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))
  }, [])

  useEffect(() => {
    // Read from localStorage on first mount
    const stored = localStorage.getItem('autoclip-theme') as Theme | null
    if (stored) {
      setTheme(stored)
      return
    }
    // Otherwise follow system preference
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    setTheme(prefersDark ? 'dark' : 'light')
  }, [])

  useEffect(() => {
    // Apply to document element for CSS data-theme selector
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark')
    } else {
      document.documentElement.removeAttribute('data-theme')
    }
    localStorage.setItem('autoclip-theme', theme)
  }, [theme])

  return { theme, toggleTheme }
}