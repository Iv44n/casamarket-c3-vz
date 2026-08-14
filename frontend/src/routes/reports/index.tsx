import { createFileRoute, Link } from '@tanstack/react-router'
import { ChevronRightIcon } from 'lucide-react'
import { Card, CardContent } from '#/components/ui/card'
import { REPORT_NAMES } from '#/server/schemas'
export const Route = createFileRoute('/reports/')({
  component: ReportsIndex
})
function ReportsIndex() {
  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight">Reportes</h1>
      <Card className="mt-4">
        <CardContent className="divide-y p-0">
          {REPORT_NAMES.map(name => (
            <Link
              key={name}
              to="/reports/$reportName"
              params={{ reportName: name }}
              className="flex items-center justify-between px-4 py-3 text-sm transition-colors first:rounded-t-xl last:rounded-b-xl hover:bg-accent/40"
            >
              {name}
              <ChevronRightIcon className="size-4 text-muted-foreground" />
            </Link>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
