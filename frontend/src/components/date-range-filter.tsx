import { CalendarIcon, XIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { DateRange } from 'react-day-picker'
import { es } from 'react-day-picker/locale'
import { Button } from '#/components/ui/button'
import { Calendar } from '#/components/ui/calendar'
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '#/components/ui/popover'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '#/components/ui/tabs'
import {
  addDaysIso,
  type DateFilter,
  firstDayOfMonthIso,
  mondayOfWeek,
  todayIsoDate
} from '#/server/schemas'

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
function parseIsoDateLocal(value: string): Date | undefined {
  const match = ISO_DATE.exec(value)
  if (!match) return undefined
  const [, year, month, day] = match
  return new Date(Number(year), Number(month) - 1, Number(day))
}
function toIsoDateLocal(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

type DatePreset = {
  key: string
  label: string
  from: string
  to: string
}
function buildDatePresets(): DatePreset[] {
  const today = todayIsoDate()
  const monday = mondayOfWeek(today)
  const lastMonthEnd = addDaysIso(firstDayOfMonthIso(today), -1)
  const lastMonthStart = firstDayOfMonthIso(lastMonthEnd)
  return [
    { key: 'today', label: 'Hoy', from: today, to: today },
    {
      key: 'yesterday',
      label: 'Ayer',
      from: addDaysIso(today, -1),
      to: addDaysIso(today, -1)
    },
    {
      key: 'last7',
      label: 'Últimos 7 días',
      from: addDaysIso(today, -6),
      to: today
    },
    {
      key: 'last14',
      label: 'Últimos 14 días',
      from: addDaysIso(today, -13),
      to: today
    },
    {
      key: 'last30',
      label: 'Últimos 30 días',
      from: addDaysIso(today, -29),
      to: today
    },
    { key: 'thisWeek', label: 'Esta semana', from: monday, to: today },
    {
      key: 'lastWeek',
      label: 'Semana pasada',
      from: addDaysIso(monday, -7),
      to: addDaysIso(monday, -1)
    },
    {
      key: 'thisMonth',
      label: 'Este mes',
      from: firstDayOfMonthIso(today),
      to: today
    },
    {
      key: 'lastMonth',
      label: 'Mes pasado',
      from: lastMonthStart,
      to: lastMonthEnd
    }
  ]
}

export function DateRangeFilter({
  date,
  dateEnd,
  onChange,
  clearLabel = 'Quitar filtro de fecha',
  disabled = false
}: {
  date: DateFilter
  dateEnd: string | undefined
  onChange: (date: DateFilter, dateEnd: string | undefined) => void
  clearLabel?: string
  disabled?: boolean
}) {
  const isRangeSelected = date !== 'all' && Boolean(dateEnd) && dateEnd !== date
  const committedRange: DateRange | undefined =
    date === 'all'
      ? undefined
      : {
          from: parseIsoDateLocal(date),
          to: dateEnd ? parseIsoDateLocal(dateEnd) : parseIsoDateLocal(date)
        }
  const [pendingRange, setPendingRange] = useState<DateRange | undefined>(
    committedRange
  )
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (disabled) setOpen(false)
  }, [disabled])
  const presets = useMemo(buildDatePresets, [])
  const activePreset =
    date !== 'all'
      ? presets.find(
          preset => preset.from === date && preset.to === (dateEnd ?? date)
        )
      : undefined
  function commitRange(from: Date, to: Date) {
    const fromIso = toIsoDateLocal(from)
    const toIso = toIsoDateLocal(to)
    onChange(fromIso, toIso !== fromIso ? toIso : undefined)
  }
  function handlePendingRangeSelect(next: DateRange | undefined) {
    setPendingRange(next)
    if (!next?.from) {
      onChange('all', undefined)
      return
    }
    if (!next.to) return
    commitRange(next.from, next.to)
  }
  function handlePresetSelect(preset: DatePreset) {
    onChange(preset.from, preset.to !== preset.from ? preset.to : undefined)
    setOpen(false)
  }
  function handleClearInPopover() {
    onChange('all', undefined)
    setOpen(false)
  }
  return (
    <div className="flex items-center gap-1">
      <Popover
        open={open}
        onOpenChange={nextOpen => {
          if (disabled) return
          setOpen(nextOpen)
          if (nextOpen) setPendingRange(committedRange)
        }}
      >
        <PopoverTrigger
          disabled={disabled}
          render={<Button variant="outline" className="font-normal" />}
        >
          <CalendarIcon data-icon="inline-start" />
          {date === 'all'
            ? 'Elegir fecha'
            : activePreset
              ? activePreset.label
              : isRangeSelected
                ? `${date} — ${dateEnd}`
                : date}
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0">
          <Tabs
            defaultValue={date === 'all' || activePreset ? 'quick' : 'range'}
          >
            <TabsList className="mx-3 mt-3">
              <TabsTrigger value="range">Rango</TabsTrigger>
              <TabsTrigger value="quick">Rápido</TabsTrigger>
            </TabsList>
            <TabsContent value="range">
              <Calendar
                mode="range"
                numberOfMonths={2}
                resetOnSelect
                selected={pendingRange}
                onSelect={handlePendingRangeSelect}
                disabled={disabled ? true : { after: new Date() }}
                locale={es}
              />
            </TabsContent>
            <TabsContent value="quick" className="flex flex-col gap-1 p-3 pt-2">
              <Button
                variant={date === 'all' ? 'secondary' : 'ghost'}
                size="sm"
                className="justify-start"
                disabled={disabled}
                onClick={handleClearInPopover}
              >
                Todos
              </Button>
              {presets.map(preset => (
                <Button
                  key={preset.key}
                  variant={
                    activePreset?.key === preset.key ? 'secondary' : 'ghost'
                  }
                  size="sm"
                  className="justify-start"
                  disabled={disabled}
                  onClick={() => handlePresetSelect(preset)}
                >
                  {preset.label}
                </Button>
              ))}
            </TabsContent>
          </Tabs>
        </PopoverContent>
      </Popover>
      {date !== 'all' && (
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={clearLabel}
          disabled={disabled}
          onClick={() => onChange('all', undefined)}
        >
          <XIcon />
        </Button>
      )}
    </div>
  )
}
