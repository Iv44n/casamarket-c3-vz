import { CalendarIcon, XIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { DateRange } from 'react-day-picker'
import { es } from 'react-day-picker/locale'
import { Button } from '#/components/ui/button'
import { Calendar } from '#/components/ui/calendar'
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from '#/components/ui/popover'
import type { DateFilter } from '#/server/schemas'

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
            : isRangeSelected
              ? `${date} — ${dateEnd}`
              : date}
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0">
          <Calendar
            mode="range"
            numberOfMonths={2}
            resetOnSelect
            selected={pendingRange}
            onSelect={handlePendingRangeSelect}
            disabled={disabled ? true : { after: new Date() }}
            locale={es}
          />
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
