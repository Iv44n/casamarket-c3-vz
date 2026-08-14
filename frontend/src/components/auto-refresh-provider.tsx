import { useRouter } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import type * as React from 'react'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState
} from 'react'
import { toast } from 'sonner'
import {
  type AutoRefreshSettings,
  intervalMs,
  loadAutoRefreshSettings,
  saveAutoRefreshSettings
} from '#/lib/auto-refresh-settings'
import { triggerRefresh } from '#/server/reports.functions'

type AutoRefreshContextValue = {
  settings: AutoRefreshSettings
  setSettings: (settings: AutoRefreshSettings) => void
  lastRunAt: Date | null
  lastError: string | null
}
const AutoRefreshContext = createContext<AutoRefreshContextValue | null>(null)
export function AutoRefreshProvider({
  children
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const refresh = useServerFn(triggerRefresh)
  const [settings, setSettingsState] = useState<AutoRefreshSettings>(
    loadAutoRefreshSettings
  )
  const [lastRunAt, setLastRunAt] = useState<Date | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined
  )
  const setSettings = useCallback((next: AutoRefreshSettings) => {
    setSettingsState(next)
    saveAutoRefreshSettings(next)
  }, [])
  useEffect(() => {
    if (!settings.enabled) return
    let cancelled = false
    const delay = intervalMs(settings.value, settings.unit)
    async function tick() {
      try {
        await refresh()
        if (cancelled) return
        setLastError(null)
        setLastRunAt(new Date())
        await router.invalidate()
      } catch (err) {
        if (cancelled) return
        const message = err instanceof Error ? err.message : String(err)
        if (!message.includes('responded 409')) {
          setLastError(message)
          toast.error(`Auto-refresh fallo: ${message}`)
        }
      } finally {
        if (!cancelled) {
          timeoutRef.current = setTimeout(tick, delay)
        }
      }
    }
    timeoutRef.current = setTimeout(tick, delay)
    return () => {
      cancelled = true
      clearTimeout(timeoutRef.current)
    }
  }, [settings, refresh, router])
  return (
    <AutoRefreshContext.Provider
      value={{ settings, setSettings, lastRunAt, lastError }}
    >
      {children}
    </AutoRefreshContext.Provider>
  )
}
export function useAutoRefresh(): AutoRefreshContextValue {
  const ctx = useContext(AutoRefreshContext)
  if (ctx === null) {
    throw new Error('useAutoRefresh must be used within an AutoRefreshProvider')
  }
  return ctx
}
