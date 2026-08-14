import { createFileRoute, Link } from '@tanstack/react-router'
import { ActivityIcon, BarChartHorizontalIcon, TableIcon } from 'lucide-react'
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle
} from '#/components/ui/card'
export const Route = createFileRoute('/')({ component: Home })
const SECTIONS = [
  {
    to: '/reports' as const,
    icon: TableIcon,
    title: 'Reportes',
    description: 'Atenciones, llamadas y contactos ya descargados de C3.'
  },
  {
    to: '/atenciones' as const,
    icon: BarChartHorizontalIcon,
    title: 'Atenciones',
    description: 'Distribucion por estado de atenciones entrantes y salientes.'
  },
  {
    to: '/status' as const,
    icon: ActivityIcon,
    title: 'Extraction status',
    description: 'Ultima corrida del scheduler, con refresh manual.'
  }
]
function Home() {
  return (
    <div>
      <h1 className="text-4xl font-bold tracking-tight">C3 Panel</h1>
      <p className="mt-2 text-lg text-muted-foreground">
        Casa Market's Contact Center Cloud data, servida por el backend FastAPI.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {SECTIONS.map(({ to, icon: Icon, title, description }) => (
          <Link key={to} to={to} className="block">
            <Card className="h-full transition-colors hover:border-primary/40 hover:bg-accent/40">
              <CardHeader>
                <Icon className="size-6 text-primary" />
                <CardTitle className="mt-2">{title}</CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
