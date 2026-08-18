import { createFileRoute, useRouter } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import { RefreshCwIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useAutoRefresh } from '#/components/auto-refresh-provider'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '#/components/ui/card'
import { Field, FieldLabel } from '#/components/ui/field'
import { Input } from '#/components/ui/input'
import { Label } from '#/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '#/components/ui/select'
import { Switch } from '#/components/ui/switch'
import type { IntervalUnit } from '#/lib/auto-refresh-settings'
import { cn } from '#/lib/utils'
import {
  getBackfillStatus,
  getContactsSyncStatus,
  getExtractionStatus,
  getHistoricalBackfillStatus,
  triggerBackfill,
  triggerContactsSyncRun,
  triggerHistoricalBackfillRun,
  triggerRefresh
} from '#/server/reports.functions'
import type { HistoricalBackfillStatus } from '#/server/schemas'
export const Route = createFileRoute('/status')({
  ssr: 'data-only',
  loader: async () => ({
    status: await getExtractionStatus(),
    backfillStatus: await getBackfillStatus(),
    contactsSyncStatus: await getContactsSyncStatus(),
    historicalBackfillStatus: await getHistoricalBackfillStatus()
  }),
  component: StatusPage
})
function StatusPage() {
  const {
    status,
    backfillStatus,
    contactsSyncStatus,
    historicalBackfillStatus
  } = Route.useLoaderData()
  const router = useRouter()
  const refresh = useServerFn(triggerRefresh)
  const [pending, setPending] = useState(false)
  const hasRun = 'started_at' in status
  async function handleRefresh() {
    setPending(true)
    try {
      await refresh()
      await router.invalidate()
      toast.success('Extraccion completada')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }
  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Extraction status</h1>
        {hasRun && (
          <Badge variant={status.ok ? 'default' : 'destructive'}>
            {status.ok ? 'ok' : 'con errores'}
          </Badge>
        )}
      </div>

      <Card className="mt-4">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-sm text-muted-foreground">
            {hasRun
              ? `Ultima corrida: ${status.finished_at}`
              : 'Sin corridas todavia'}
          </CardTitle>
          <Button onClick={handleRefresh} disabled={pending}>
            <RefreshCwIcon
              data-icon="inline-start"
              className={cn(pending && 'animate-spin')}
            />
            {pending ? 'Corriendo...' : 'Refresh ahora'}
          </Button>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs">
            {JSON.stringify(status, null, 2)}
          </pre>
        </CardContent>
      </Card>

      <AutoRefreshSettingsCard />

      <BackfillCard backfillStatus={backfillStatus} />

      <ContactsSyncCard contactsSyncStatus={contactsSyncStatus} />

      <HistoricalBackfillCard initialStatus={historicalBackfillStatus} />
    </div>
  )
}
function BackfillCard({
  backfillStatus
}: {
  backfillStatus: Awaited<ReturnType<typeof getBackfillStatus>>
}) {
  const router = useRouter()
  const backfill = useServerFn(triggerBackfill)
  const [date, setDate] = useState('')
  const [pending, setPending] = useState(false)
  const hasRun = 'started_at' in backfillStatus
  async function handleBackfill() {
    if (!date) {
      toast.error('Elegi una fecha primero.')
      return
    }
    setPending(true)
    try {
      await backfill({ data: { date } })
      await router.invalidate()
      toast.success(`Backfill de ${date} completado.`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }
  return (
    <Card className="mt-4">
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Backfill de un dia especifico</CardTitle>
          <CardDescription>
            Vuelve a pedirle a C3 un dia puntual (atenciones y llamadas, no
            contactos -- su export no tiene rango de fechas) y sobreescribe el
            archivo de ese dia. Util si se elimino un archivo o el refresh de
            ese dia no corrio.
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Input
            type="date"
            value={date}
            onValueChange={setDate}
            className="w-40"
          />
          <Button
            onClick={handleBackfill}
            disabled={pending}
            variant="secondary"
          >
            <RefreshCwIcon
              data-icon="inline-start"
              className={cn(pending && 'animate-spin')}
            />
            {pending ? 'Corriendo...' : 'Backfill'}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          {hasRun
            ? `Ultimo backfill: ${backfillStatus.target_date} (${backfillStatus.finished_at})`
            : 'Sin corridas todavia'}
        </p>
        <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-4 text-xs">
          {JSON.stringify(backfillStatus, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}
function ContactsSyncCard({
  contactsSyncStatus
}: {
  contactsSyncStatus: Awaited<ReturnType<typeof getContactsSyncStatus>>
}) {
  const router = useRouter()
  const sync = useServerFn(triggerContactsSyncRun)
  const [pending, setPending] = useState(false)
  const hasRun = 'started_at' in contactsSyncStatus
  async function handleSync() {
    setPending(true)
    try {
      await sync()
      await router.invalidate()
      toast.success('Sincronizacion de contactos completada.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }
  return (
    <Card className="mt-4">
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Sincronizar contactos</CardTitle>
          <CardDescription>
            El refresh de arriba ya no descarga 'contacts' (es un roster
            completo de ~7.5k filas, no vale la pena en cada corrida de 5
            minutos) -- este boton lo trae bajo demanda.
          </CardDescription>
        </div>
        <Button onClick={handleSync} disabled={pending} variant="secondary">
          <RefreshCwIcon
            data-icon="inline-start"
            className={cn(pending && 'animate-spin')}
          />
          {pending ? 'Sincronizando...' : 'Sincronizar ahora'}
        </Button>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          {hasRun
            ? `Ultima sincronizacion: ${contactsSyncStatus.finished_at}`
            : 'Sin corridas todavia'}
        </p>
        <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-4 text-xs">
          {JSON.stringify(contactsSyncStatus, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}
const HISTORICAL_BACKFILL_POLL_MS = 3000
function HistoricalBackfillCard({
  initialStatus
}: {
  initialStatus: HistoricalBackfillStatus
}) {
  const router = useRouter()
  const startBackfill = useServerFn(triggerHistoricalBackfillRun)
  const getStatus = useServerFn(getHistoricalBackfillStatus)
  const [status, setStatus] = useState(initialStatus)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (status.phase !== 'running') return
    timeoutRef.current = setTimeout(async () => {
      const next = await getStatus()
      setStatus(next)
      if (next.phase !== 'running') {
        await router.invalidate()
      }
    }, HISTORICAL_BACKFILL_POLL_MS)
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [status, getStatus, router])
  async function handleStart() {
    if (
      !window.confirm(
        'Esto le pide a C3 los ultimos 90 dias (el maximo permitido) para ' +
          '5 reportes y puede tardar varios minutos. Pensado para correr una ' +
          'sola vez en la vida de la app -- ¿continuar?'
      )
    ) {
      return
    }
    const next = await startBackfill()
    setStatus(next)
  }
  const isRunning = status.phase === 'running'
  return (
    <Card className="mt-4">
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Backfill historico (90 dias, una sola vez)</CardTitle>
          <CardDescription>
            Carga inicial del historico persistente: pide a C3 un rango amplio
            (hasta el limite de 3 meses que C3 permite) para atenciones,
            llamadas y transferencias, y hace upsert por ID en la base historica
            -- asi un caso que se cierra dias despues de creado queda con su
            estado real, no congelado en el dia que se creo. Despues de esta
            corrida el historico se sigue llenando solo con el refresh normal de
            cada 5 minutos, sin nada mas que tocar aca.
          </CardDescription>
        </div>
        <Button onClick={handleStart} disabled={isRunning} variant="secondary">
          <RefreshCwIcon
            data-icon="inline-start"
            className={cn(isRunning && 'animate-spin')}
          />
          {isRunning ? 'Corriendo...' : 'Iniciar backfill'}
        </Button>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          {status.phase === 'idle' && 'Sin corridas todavia.'}
          {status.phase === 'running' && `En curso desde ${status.started_at}.`}
          {status.phase === 'done' &&
            `Ultima corrida: ${status.finished_at} (ok: ${status.result?.ok}).`}
          {status.phase === 'error' && `Ultimo error: ${status.error}`}
        </p>
        <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-4 text-xs">
          {JSON.stringify(status, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}
const UNIT_LABEL: Record<IntervalUnit, string> = {
  seconds: 'segundos',
  minutes: 'minutos',
  hours: 'horas'
}
function AutoRefreshSettingsCard() {
  const { settings, setSettings, lastRunAt, lastError } = useAutoRefresh()
  const [draftValue, setDraftValue] = useState(String(settings.value))
  const [draftUnit, setDraftUnit] = useState<IntervalUnit>(settings.unit)
  const [draftEnabled, setDraftEnabled] = useState(settings.enabled)
  function handleSave() {
    const value = Number(draftValue)
    if (!Number.isFinite(value) || value <= 0) {
      toast.error('El intervalo debe ser un numero mayor a 0.')
      return
    }
    setSettings({ enabled: draftEnabled, value, unit: draftUnit })
    toast.success('Intervalo de auto-refresh actualizado.')
  }
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Auto-refresh</CardTitle>
        <CardDescription>
          No hay cron en el servidor -- el cliente llama a /extraction/refresh
          en este intervalo mientras esta pestaña este abierta. Cerrar la
          pestaña pausa la extraccion automatica.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <Switch
            id="auto-refresh-enabled"
            checked={draftEnabled}
            onCheckedChange={setDraftEnabled}
          />
          <Label htmlFor="auto-refresh-enabled">Activado</Label>
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <Field className="w-24">
            <FieldLabel htmlFor="auto-refresh-value">Cada</FieldLabel>
            <Input
              id="auto-refresh-value"
              type="number"
              min={1}
              value={draftValue}
              onChange={e => setDraftValue(e.target.value)}
            />
          </Field>

          <Select
            value={draftUnit}
            onValueChange={value => setDraftUnit(value as IntervalUnit)}
          >
            <SelectTrigger className="w-32">
              <SelectValue>
                {(value: IntervalUnit) => UNIT_LABEL[value]}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="seconds">segundos</SelectItem>
              <SelectItem value="minutes">minutos</SelectItem>
              <SelectItem value="hours">horas</SelectItem>
            </SelectContent>
          </Select>

          <Button onClick={handleSave}>Guardar</Button>
        </div>

        <p className="text-xs text-muted-foreground">
          {settings.enabled
            ? `Activo: cada ${settings.value} ${UNIT_LABEL[settings.unit]}.`
            : 'Desactivado.'}{' '}
          {lastRunAt &&
            `Ultimo auto-refresh: ${lastRunAt.toLocaleTimeString()}.`}
        </p>
        {lastError && (
          <p className="text-xs text-destructive">
            Ultimo error de auto-refresh: {lastError}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
