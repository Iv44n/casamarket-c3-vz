import { createTheme, ThemeProvider } from '@mui/material/styles'
import type * as React from 'react'
import { useEffect, useMemo, useState } from 'react'

function useIsDarkMode(): boolean {
  const [isDark, setIsDark] = useState(false)
  useEffect(() => {
    const root = document.documentElement
    const update = () => setIsDark(root.classList.contains('dark'))
    update()
    const observer = new MutationObserver(update)
    observer.observe(root, { attributes: true, attributeFilter: ['class'] })
    return () => observer.disconnect()
  }, [])
  return isDark
}
export function ChartThemeProvider({
  children
}: {
  children: React.ReactNode
}) {
  const isDark = useIsDarkMode()
  const theme = useMemo(
    () =>
      createTheme({
        palette: {
          mode: isDark ? 'dark' : 'light',
          background: {
            paper: 'var(--color-card)',
            default: 'var(--color-background)'
          },
          text: {
            primary: 'var(--color-foreground)',
            secondary: 'var(--color-muted-foreground)'
          },
          divider: 'var(--color-border)'
        }
      }),
    [isDark]
  )
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>
}
