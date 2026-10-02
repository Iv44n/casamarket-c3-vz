import { Link } from '@tanstack/react-router'
import {
  ArrowDownWideNarrowIcon,
  ArrowUpNarrowWideIcon,
  ChevronRightIcon,
  UserRoundIcon
} from 'lucide-react'
import { useState } from 'react'
import { CopyButton } from '#/components/copy-button'
import { LoadError } from '#/components/load-error'
import { Avatar, AvatarFallback } from '#/components/ui/avatar'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '#/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '#/components/ui/select'
import { Skeleton } from '#/components/ui/skeleton'
import type { ClientList } from '#/lib/attentions-analytics'
import { cn } from '#/lib/utils'
import {
  type AgentesFilter,
  CLIENT_ORDERS,
  type ClientCaseCount,
  type ClientOrder
} from '#/server/schemas'

// Un mes de historial son ~2.000 clientes: se pintan de a poco en vez de todos de golpe.
const PAGE_SIZE = 50
const ORDER_LABEL: Record<ClientOrder, string> = {
  desc: 'Casos: de mayor a menor',
  asc: 'Casos: de menor a mayor'
}
const SKELETON_ROWS = [0, 1, 2, 3, 4, 5]
const UNKNOWN_NAME_LABEL = 'Sin nombre'

// C3 a veces manda "-" en vez de dejar el nombre vacio.
function isBlankName(name: string): boolean {
  const trimmed = name.trim()
  return trimmed === '' || trimmed === '-'
}

function displayName(client: ClientCaseCount): string {
  return isBlankName(client.name) ? UNKNOWN_NAME_LABEL : client.name.trim()
}

// Dos primeras palabras que empiecen con una letra (se saltan emojis y simbolos sueltos);
// [...word][0] toma el primer code point, no la mitad de un par subrogado.
function initialsOf(name: string): string | null {
  const words = name.split(/\s+/).filter(word => /^\p{L}/u.test(word))
  if (words.length === 0) return null
  return words
    .slice(0, 2)
    .map(word => [...word][0])
    .join('')
    .toUpperCase()
}

// 51987654321 -> +51 987 654 321 ; 987654321 -> 987 654 321 ; cualquier otro largo, tal cual
// (hay unos pocos numeros con 10, 12 o 13 digitos que no se pueden agrupar con seguridad).
function formatPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('51')) {
    return `+51 ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`
  }
  if (digits.length === 9) {
    return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`
  }
  return phone
}

function ClientListSkeleton() {
  return (
    <div className="flex flex-col gap-4 rounded-xl border p-3">
      {SKELETON_ROWS.map(row => (
        <div key={row} className="flex items-center gap-3">
          <Skeleton className="size-8 shrink-0 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-6 w-8" />
        </div>
      ))}
    </div>
  )
}

type DetailRange = {
  date: string
  dateEnd: string | undefined
  agentes: AgentesFilter
}

// Se superpone al enlace que cubre la fila (relative z-10). Con mouse solo aparece al pasar por
// la fila o al enfocarla con el teclado, para no llenar la lista de iconos; en pantallas tactiles
// (sin hover) esta siempre visible.
const ROW_COPY_BUTTON_CLASS =
  'relative z-10 -my-1 pointer-fine:opacity-0 pointer-fine:group-focus-within:opacity-100 pointer-fine:group-hover:opacity-100'

// La fila entera es un enlace a la lista de casos de ese cliente (/atenciones, pestaña Demoras)
// con el mismo rango y los mismos agentes que se estan viendo aca -- asi el "N casos" de la fila
// es el "N atenciones" que se ve al llegar. Como una fila con botones de copiar adentro no puede
// ser un <a> (no se anidan controles interactivos), el <Link> es solo el nombre y su ::after
// (after:absolute after:inset-0) se estira sobre todo el <li>; los botones quedan por encima.
// preload={false} a proposito: la precarga por hover (default del router) correria el loader de
// /atenciones, que baja el historial completo del rango, cada vez que el mouse pasa por una fila.
function ClientRow({
  client,
  range
}: {
  client: ClientCaseCount
  range: DetailRange
}) {
  const name = displayName(client)
  const blankName = isBlankName(client.name)
  const initials = blankName ? null : initialsOf(client.name)
  const casesLabel = client.count === 1 ? 'caso' : 'casos'
  const detailLabel = `Ver ${client.count === 1 ? 'el caso' : `los ${client.count} casos`} de ${name}`
  return (
    <li className="group relative flex items-center gap-3 border-b px-3 py-2.5 transition-colors last:border-b-0 hover:bg-accent has-[a:focus-visible]:bg-accent">
      <Avatar aria-hidden>
        <AvatarFallback className="bg-primary/10 font-medium text-primary">
          {initials ?? <UserRoundIcon className="size-4" />}
        </AvatarFallback>
      </Avatar>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-1">
          <Link
            to="/atenciones"
            search={{
              view: 'demoras',
              date: range.date,
              dateEnd: range.dateEnd !== range.date ? range.dateEnd : undefined,
              agentes: range.agentes,
              cliente: client.key,
              clienteNombre: name
            }}
            preload={false}
            title={detailLabel}
            aria-label={detailLabel}
            className={cn(
              'min-w-0 truncate font-medium outline-none after:absolute after:inset-0 focus-visible:after:ring-[3px] focus-visible:after:ring-inset focus-visible:after:ring-ring/50',
              blankName && 'text-muted-foreground italic'
            )}
          >
            {name}
          </Link>
          {!blankName && (
            <CopyButton
              text={client.name.trim()}
              noun="nombre"
              subject={`de ${name}`}
              className={ROW_COPY_BUTTON_CLASS}
            />
          )}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
          {client.phone ? (
            <span className="flex items-center gap-1">
              <span className="tabular-nums">{formatPhone(client.phone)}</span>
              <CopyButton
                text={client.phone}
                noun="teléfono"
                subject={`de ${name}`}
                className={ROW_COPY_BUTTON_CLASS}
              />
            </span>
          ) : (
            <span className="italic">Sin teléfono</span>
          )}
          {client.plan ? (
            <Badge variant="secondary" className="max-w-40">
              <span className="truncate">{client.plan}</span>
            </Badge>
          ) : (
            <span className="italic">Sin plan</span>
          )}
        </div>
      </div>
      <span className="flex shrink-0 flex-col items-end gap-1 leading-none">
        <span className="text-xl font-bold tabular-nums">{client.count}</span>
        <span className="text-[11px] text-muted-foreground">{casesLabel}</span>
      </span>
      <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
    </li>
  )
}

// Estado propio (cuantas filas se muestran) para que se reinicie solo: el padre lo remonta
// (key) al cambiar el orden, y al cambiar el rango pasa antes por el skeleton.
function ClientRows({
  clients,
  range
}: {
  clients: ClientCaseCount[]
  range: DetailRange
}) {
  const [visible, setVisible] = useState(PAGE_SIZE)
  const remaining = clients.length - visible
  return (
    <div className="max-h-[28rem] overflow-y-auto rounded-xl border">
      <ul>
        {clients.slice(0, visible).map(client => (
          <ClientRow key={client.key} client={client} range={range} />
        ))}
      </ul>
      {remaining > 0 && (
        <Button
          variant="ghost"
          size="sm"
          className="w-full rounded-none"
          onClick={() => setVisible(current => current + PAGE_SIZE)}
        >
          Mostrar más ({remaining} restantes)
        </Button>
      )}
    </div>
  )
}

export function ClientListCard({
  list,
  order,
  onOrderChange,
  loading,
  error,
  onRetry,
  date,
  dateEnd,
  agentes
}: {
  list: ClientList
  order: ClientOrder
  onOrderChange: (order: ClientOrder) => void
  loading: boolean
  error: string | null
  onRetry: () => void
} & DetailRange) {
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Clientes</CardTitle>
        <CardDescription>
          Clientes con casos en el rango (y los agentes) elegidos arriba. Haz
          clic en uno para ver sus casos.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <ClientListSkeleton />
        ) : error ? (
          <LoadError
            title="No se pudo cargar la lista de clientes."
            message={error}
            onRetry={onRetry}
            className="h-[280px]"
          />
        ) : list.totalClients === 0 ? (
          <p className="text-sm text-muted-foreground">
            Sin clientes con casos en el rango elegido.
          </p>
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <div>
                  <span className="text-xs text-muted-foreground">
                    Clientes
                  </span>
                  <p className="font-semibold tabular-nums">
                    {list.totalClients}
                  </p>
                </div>
                <div className="h-6 w-px bg-border" />
                <div>
                  <span className="text-xs text-muted-foreground">Casos</span>
                  <p className="font-semibold tabular-nums">
                    {list.totalCases}
                  </p>
                </div>
              </div>
              <Select
                value={order}
                onValueChange={value => {
                  if (value) onOrderChange(value as ClientOrder)
                }}
              >
                <SelectTrigger
                  className="w-60"
                  aria-label="Ordenar clientes por número de casos"
                >
                  <SelectValue>
                    {(value: ClientOrder) => (
                      <>
                        {value === 'desc' ? (
                          <ArrowDownWideNarrowIcon />
                        ) : (
                          <ArrowUpNarrowWideIcon />
                        )}
                        {ORDER_LABEL[value]}
                      </>
                    )}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {CLIENT_ORDERS.map(option => (
                    <SelectItem key={option} value={option}>
                      {ORDER_LABEL[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <ClientRows
              key={order}
              clients={list.clients}
              range={{ date, dateEnd, agentes }}
            />
          </>
        )}
      </CardContent>
    </Card>
  )
}
