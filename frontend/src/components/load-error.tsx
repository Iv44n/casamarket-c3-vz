import { RefreshCwIcon, TriangleAlertIcon } from 'lucide-react'
import { Button } from '#/components/ui/button'
import { cn } from '#/lib/utils'

export function LoadError({
  title,
  message,
  onRetry,
  className
}: {
  title: string
  message: string
  onRetry: () => void
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 text-center',
        className
      )}
    >
      <TriangleAlertIcon className="size-8 text-destructive" />
      <p className="text-sm font-medium">{title}</p>
      <p className="rounded-md bg-muted px-2.5 py-1 font-mono text-xs text-muted-foreground">
        {message}
      </p>
      <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
        <RefreshCwIcon data-icon="inline-start" />
        Reintentar
      </Button>
    </div>
  )
}
