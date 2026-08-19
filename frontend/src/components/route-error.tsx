import type { ErrorComponentProps } from '@tanstack/react-router'
import { useRouter } from '@tanstack/react-router'
import { TriangleAlertIcon } from 'lucide-react'
import { useState } from 'react'
import { Button } from '#/components/ui/button'

export function RouteError({ error }: ErrorComponentProps) {
  const router = useRouter()
  const [showDetails, setShowDetails] = useState(!import.meta.env.PROD)
  const message =
    error instanceof Error ? error.message : 'Ocurrio un error inesperado.'
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 py-24 text-center">
      <TriangleAlertIcon className="size-6 text-destructive" />
      <p className="text-sm text-muted-foreground">
        Ocurrio un error al cargar esta pagina.
      </p>
      {showDetails && (
        <p className="max-w-md text-xs text-muted-foreground/80">{message}</p>
      )}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowDetails(v => !v)}
        >
          {showDetails ? 'Ocultar detalle' : 'Mostrar detalle'}
        </Button>
        <Button variant="outline" onClick={() => router.invalidate()}>
          Reintentar
        </Button>
      </div>
    </div>
  )
}
