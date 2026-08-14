import { Link, useRouterState } from '@tanstack/react-router'
import { ModeToggle } from '#/components/mode-toggle'
import { cn } from '#/lib/utils'

const NAV_ITEMS = [
  { to: '/reports', label: 'Reportes' },
  { to: '/atenciones', label: 'Atenciones' },
  { to: '/incidencias', label: 'Incidencias' },
  { to: '/status', label: 'Extraction status' }
] as const
export function SiteHeader() {
  const pathname = useRouterState({ select: state => state.location.pathname })
  const isWallboard = pathname === '/atenciones'
  return (
    <header className="border-b">
      <div
        className={cn(
          'flex h-14 items-center justify-between px-4',
          isWallboard ? 'w-full px-6' : 'mx-auto max-w-5xl'
        )}
      >
        <Link to="/" className="font-semibold">
          C3 Panel
        </Link>
        <nav className="flex items-center gap-4">
          {NAV_ITEMS.map(item => (
            <Link
              key={item.to}
              to={item.to}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              activeProps={{ className: 'text-foreground font-medium' }}
            >
              {item.label}
            </Link>
          ))}
          <ModeToggle />
        </nav>
      </div>
    </header>
  )
}
