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
  type BenchmarkScheduleSettings,
  limaDateIso,
  loadBenchmarkScheduleSettings,
  msUntilNextRun,
  saveBenchmarkScheduleSettings
} from '#/lib/benchmark-schedule-settings'
import { triggerBenchmarkRun } from '#/server/reports.functions'

type BenchmarkScheduleContextValue = {
  settings: BenchmarkScheduleSettings
  setSettings: (settings: BenchmarkScheduleSettings) => void
  lastRunAt: Date | null
  lastError: string | null
}
const BenchmarkScheduleContext =
  createContext<BenchmarkScheduleContextValue | null>(null)

// msUntilNextRun nunca devuelve "en el pasado" -- si la hora de hoy ya paso, apunta a la
// misma hora mañana, lo cual tipicamente supera este umbral. Un delay por encima de esto es
// la señal de "hoy ya paso" que dispara el catch-up en vez de esperar hasta mañana.
const TARGET_ALREADY_PASSED_THRESHOLD_MS = 12 * 60 * 60 * 1000
// Debounce corto antes del catch-up al abrir la pestaña -- no instantaneo, para que no se
// sienta como un efecto secundario oculto de solo cargar la pagina.
const CATCH_UP_DEBOUNCE_MS = 10_000

export function BenchmarkScheduleProvider({
  children
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const runBenchmarks = useServerFn(triggerBenchmarkRun)
  const [settings, setSettingsState] = useState<BenchmarkScheduleSettings>(
    loadBenchmarkScheduleSettings
  )
  const [lastRunAt, setLastRunAt] = useState<Date | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined
  )
  const setSettings = useCallback((next: BenchmarkScheduleSettings) => {
    setSettingsState(next)
    saveBenchmarkScheduleSettings(next)
  }, [])

  useEffect(() => {
    if (!settings.enabled) return
    let cancelled = false

    function scheduleNext() {
      const delay = msUntilNextRun(new Date(), settings.timeOfDay)
      timeoutRef.current = setTimeout(fire, delay)
    }

    async function fire() {
      try {
        await runBenchmarks({ data: {} })
        if (cancelled) return
        setLastError(null)
        setLastRunAt(new Date())
        setSettings({
          ...settings,
          lastTriggeredDateIso: limaDateIso(new Date())
        })
        await router.invalidate()
        toast.success('Benchmarks diarios: corrida disparada.')
      } catch (err) {
        if (cancelled) return
        const message = err instanceof Error ? err.message : String(err)
        if (!message.includes('responded 409')) {
          setLastError(message)
          toast.error(`Benchmark diario fallo: ${message}`)
        }
      } finally {
        if (!cancelled) scheduleNext()
      }
    }

    const today = limaDateIso(new Date())
    const alreadyFiredToday = settings.lastTriggeredDateIso === today
    const delay = msUntilNextRun(new Date(), settings.timeOfDay)
    const targetAlreadyPassedToday = delay > TARGET_ALREADY_PASSED_THRESHOLD_MS
    timeoutRef.current = setTimeout(
      fire,
      targetAlreadyPassedToday && !alreadyFiredToday
        ? CATCH_UP_DEBOUNCE_MS
        : delay
    )

    return () => {
      cancelled = true
      clearTimeout(timeoutRef.current)
    }
  }, [settings, runBenchmarks, router, setSettings])

  return (
    <BenchmarkScheduleContext.Provider
      value={{ settings, setSettings, lastRunAt, lastError }}
    >
      {children}
    </BenchmarkScheduleContext.Provider>
  )
}
export function useBenchmarkSchedule(): BenchmarkScheduleContextValue {
  const ctx = useContext(BenchmarkScheduleContext)
  if (ctx === null) {
    throw new Error(
      'useBenchmarkSchedule must be used within a BenchmarkScheduleProvider'
    )
  }
  return ctx
}
