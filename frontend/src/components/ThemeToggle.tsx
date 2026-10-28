import { useTheme } from '../hooks/useTheme'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      onClick={toggleTheme}
      className="btn btn-ghost p-2"
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={isDark ? 'Light mode' : 'Dark mode'}
    >
      {isDark ? (
        <svg
          className="w-5 h-5 text-ink-800"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M12 3v1m0 16v1m9-9h1m-4 0h1m-6 4a1 1 0 110-2 1 1 0 010 2zm7-4a1 1 0 110-2 1 1 0 010 2zm-9 4a1 1 0 100-2 1 1 0 000 2z" />
        </svg>
      ) : (
        <svg
          className="w-5 h-5 text-accent-600"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          <path d="M12 3v1m0 16v1m9-9h-1M4 22h3m-4.354-4.354l.707-.707m15.157 1.152l-.707-.707M5.172 5.172.636 5.636m14.736 1.464L9.486 5.636M14 9v1m0 16v1m-7-9h1m-5 0h1m5 9v1m0-16v1" />
        </svg>
      )}
    </button>
  )
}