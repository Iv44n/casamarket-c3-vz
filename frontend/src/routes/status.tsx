import { createFileRoute, useRouter } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import { DownloadIcon, RefreshCwIcon, Trash2Icon } from 'lucide-react'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '#/components/ui/table'
import type { IntervalUnit } from '#/lib/auto-refresh-settings'
import { cn } from '#/lib/utils'
import {
  deleteFile,
  downloadFile,
  getBackfillStatus,
  getDownloadedFiles,
  getExtractionStatus,
  getMassiveExtractionStatus,
  triggerBackfill,
  triggerMassiveRefresh,
  triggerRefresh
} from '#/server/reports.functions'
import type { DownloadedFile } from '#/server/schemas'
export const Route = createFileRoute('/status')({
  ssr: 'data-only',
  loader: async () => ({
    status: await getExtractionStatus(),
    massiveStatus: await getMassiveExtractionStatus(),
    backfillStatus: await getBackfillStatus(),
    files: await getDownloadedFiles()
  }),
  component: StatusPage
})
function StatusPage() {
  const { status, massiveStatus, backfillStatus, files } = Route.useLoaderData()
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

      <BackfillCard backfillStatus={backfillStatus} />

      <DownloadedFilesCard files={files} />
    </div>
  )
}
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}
function DownloadedFilesCard({ files }: { files: DownloadedFile[] }) {
  const router = useRouter()
  const removeFile = useServerFn(deleteFile)
  const fetchFileDownload = useServerFn(downloadFile)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)
  const sorted = [...files].sort(
    (a, b) =>
      b.date.localeCompare(a.date) || a.report_name.localeCompare(b.report_name)
  )
  async function handleDelete(filename: string) {
    if (
      !window.confirm(
        `Eliminar '${filename}'? Esta accion no se puede deshacer.`
      )
    ) {
      return
    }
    setDeleting(filename)
    try {
      await removeFile({ data: { filename } })
      await router.invalidate()
      toast.success(`'${filename}' eliminado.`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setDeleting(null)
    }
  }
  async function handleDownload(filename: string) {
    setDownloading(filename)
    try {
      const response = await fetchFileDownload({ data: { filename } })
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setDownloading(null)
    }
  }
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Archivos descargados</CardTitle>
        <CardDescription>
          Un archivo por reporte por dia -- se acumulan indefinidamente, nada
          los borra automaticamente. El filtro de fecha de /atenciones lee de
          todos ellos, no solo del mas reciente.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Todavia no se descargo ningun archivo.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Reporte</TableHead>
                <TableHead>Fecha</TableHead>
                <TableHead>Archivo</TableHead>
                <TableHead>Tamaño</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map(file => (
                <TableRow key={file.filename}>
                  <TableCell>{file.report_name}</TableCell>
                  <TableCell>{file.date}</TableCell>
                  <TableCell
                    className="max-w-64 truncate"
                    title={file.filename}
                  >
                    {file.filename}
                  </TableCell>
                  <TableCell>{formatBytes(file.size_bytes)}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Descargar ${file.filename}`}
                      disabled={downloading === file.filename}
                      onClick={() => handleDownload(file.filename)}
                    >
                      <DownloadIcon
                        className={cn(
                          downloading === file.filename && 'animate-pulse'
                        )}
                      />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Eliminar ${file.filename}`}
                      disabled={deleting === file.filename}
                      onClick={() => handleDelete(file.filename)}
                    >
                      <Trash2Icon
                        className={cn(
                          deleting === file.filename && 'animate-pulse'
                        )}
                      />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
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
