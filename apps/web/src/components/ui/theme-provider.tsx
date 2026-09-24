import * as React from 'react'

/** The theme actually applied to the document. */
export type Theme = 'light' | 'dark'

/** What the user chose — `system` follows the OS setting. */
export type ThemePreference = Theme | 'system'

type ThemeContextValue = {
  /** The resolved theme (`system` already applied). */
  theme: Theme
  /** The user's stored choice. */
  preference: ThemePreference
  setTheme: (theme: ThemePreference) => void
  toggleTheme: () => void
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null)

const STORAGE_KEY = 'ui-theme'

function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

const DARK_QUERY = '(prefers-color-scheme: dark)'

function systemTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

function isPreference(value: string | null): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

export function ThemeProvider({
  children,
  defaultTheme = 'light',
}: {
  children: React.ReactNode
  defaultTheme?: ThemePreference
}) {
  const [preference, setPreferenceState] = React.useState<ThemePreference>(defaultTheme)
  const [system, setSystem] = React.useState<Theme>('light')

  const theme = preference === 'system' ? system : preference

  // Read the persisted preference on mount (SSR-safe: runs only in the browser).
  React.useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    setPreferenceState(isPreference(stored) ? stored : defaultTheme)
    setSystem(systemTheme())
  }, [defaultTheme])

  // Follow the OS while the preference is `system`.
  React.useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia(DARK_QUERY)
    const onChange = (event: MediaQueryListEvent) => setSystem(event.matches ? 'dark' : 'light')
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  React.useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const setTheme = React.useCallback((next: ThemePreference) => {
    setPreferenceState(next)
    if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, next)
  }, [])

  const value = React.useMemo<ThemeContextValue>(
    () => ({
      theme,
      preference,
      setTheme,
      // The topbar toggle is a two-way switch: it commits the opposite of what
      // is currently showing, leaving `system` behind deliberately.
      toggleTheme: () => setTheme(theme === 'dark' ? 'light' : 'dark'),
    }),
    [theme, preference, setTheme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = React.useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}
