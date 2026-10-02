import { CheckIcon, CopyIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '#/components/ui/button'
import { cn } from '#/lib/utils'

const COPIED_FEEDBACK_MS = 1500

// Boton de icono que copia `text` al portapapeles y lo confirma con el check en el propio boton
// y un aviso (con el texto copiado). `noun` va en masculino singular ("nombre", "teléfono"):
// con el se arman "Copiar teléfono", "Teléfono copiado" y "No se pudo copiar el teléfono".
// `subject` completa el nombre accesible ("de Ana Cruz", "del cliente").
export function CopyButton({
  text,
  noun,
  subject,
  className
}: {
  text: string
  noun: string
  subject?: string
  className?: string
}) {
  const [copied, setCopied] = useState(false)
  const resetTimerRef = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(resetTimerRef.current), [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Sin permiso del navegador, o contexto no seguro (http fuera de localhost).
      toast.error(`No se pudo copiar el ${noun}.`, { id: 'copy' })
      return
    }
    // Mismo id: copiar varias veces seguidas reemplaza el aviso en vez de apilarlos.
    toast.success(`${noun.charAt(0).toUpperCase()}${noun.slice(1)} copiado`, {
      id: 'copy',
      description: text
    })
    setCopied(true)
    window.clearTimeout(resetTimerRef.current)
    resetTimerRef.current = window.setTimeout(
      () => setCopied(false),
      COPIED_FEEDBACK_MS
    )
  }

  return (
    <Button
      variant="ghost"
      size="icon-xs"
      onClick={copy}
      title={`Copiar ${noun}`}
      aria-label={`Copiar ${noun}${subject ? ` ${subject}` : ''}`}
      className={cn('text-muted-foreground', className)}
    >
      {copied ? <CheckIcon className="text-emerald-600" /> : <CopyIcon />}
    </Button>
  )
}
