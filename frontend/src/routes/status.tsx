import { createFileRoute, useRouter } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import { RefreshCwIcon } from 'lucide-react'
import { useState } from 'react'
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
  getExtractionStatus,
  getMassiveExtractionStatus,
  triggerMassiveRefresh,
  triggerRefresh
} from '#/server/reports.functions'
export const Route = createFileRoute('/status')({
  ssr: 'data-only',
  loader: async () => ({
    status: await getExtractionStatus(),
    massiveStatus: await getMassiveExtractionStatus()
  }),
  component: StatusPage
})
function StatusPage() {
  const { status, massiveStatus } = Route.useLoaderData()
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

      <MassiveRefreshCard massiveStatus={massiveStatus} />
    </div>
  )
}
function MassiveRefreshCard({
  massiveStatus
}: {
  massiveStatus: Awaited<ReturnType<typeof getMassiveExtractionStatus>>
}) {
  const router = useRouter()
  const refreshMassive = useServerFn(triggerMassiveRefresh)
  const [pending, setPending] = useState(false)
  const hasRun = 'started_at' in massiveStatus
  async function handleRefresh() {
    setPending(true)
    try {
      await refreshMassive()
      await router.invalidate()
      toast.success('Paso del reporte masivo ejecutado')
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
          <CardTitle>Reporte masivo (atenciones)</CardTitle>
          <CardDescription>
            Ruta dedicada y separada del refresh de arriba -- nunca corre
            automaticamente, un job masivo en C3 puede demorar horas. Cada click
            avanza un solo paso del ciclo (encolar, esperar, o descargar y
            alternar de sentido).
          </CardDescription>
        </div>
        <Button onClick={handleRefresh} disabled={pending} variant="secondary">
          <RefreshCwIcon
            data-icon="inline-start"
            className={cn(pending && 'animate-spin')}
          />
          {pending ? 'Ejecutando...' : 'Ejecutar paso'}
        </Button>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          {hasRun
            ? `Ultimo paso: ${massiveStatus.finished_at}`
            : 'Sin corridas todavia'}
        </p>
        <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-4 text-xs">
          {JSON.stringify(massiveStatus, null, 2)}
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
