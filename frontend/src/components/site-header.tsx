import { Link } from '@tanstack/react-router'
import { ModeToggle } from '#/components/mode-toggle'

const NAV_ITEMS = [
  { to: '/reports', label: 'Reportes' },
  { to: '/atenciones', label: 'Atenciones' },
  { to: '/status', label: 'Extraction status' }
] as const
export function SiteHeader() {
  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
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
