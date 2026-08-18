import { Loader2Icon } from 'lucide-react'

export function RoutePending() {
  return (
    <div className="flex flex-1 items-center justify-center py-24 text-muted-foreground">
      <Loader2Icon className="size-6 animate-spin" />
    </div>
  )
}
