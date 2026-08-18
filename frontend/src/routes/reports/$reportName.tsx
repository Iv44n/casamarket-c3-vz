import { Await, createFileRoute, Link, notFound } from '@tanstack/react-router'
import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'
import { Badge } from '#/components/ui/badge'
import { buttonVariants } from '#/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '#/components/ui/card'
import { Skeleton } from '#/components/ui/skeleton'
import { Table, TableBody, TableCell, TableRow } from '#/components/ui/table'
import { cn } from '#/lib/utils'
import { getReportRows, getReportSummary } from '#/server/reports.functions'
import {
  REPORT_NAMES,
  type ReportName,
  type ReportRow,
  type ReportSummary,
  reportSearchSchema
} from '#/server/schemas'

type ReportLoaderData =
  | {
      reportName: ReportName
      rows: null
      summaryPromise: null
    }
  | {
      reportName: ReportName
      rows: ReportRow[]
      summaryPromise: Promise<ReportSummary | null>
    }
export const Route = createFileRoute('/reports/$reportName')({
  validateSearch: reportSearchSchema,
  ssr: false,
  loader: async ({ params }): Promise<ReportLoaderData> => {
    if (!REPORT_NAMES.includes(params.reportName as ReportName)) {
      throw notFound()
    }
    const reportName = params.reportName as ReportName
    const rows = await getReportRows({ data: { reportName } })
    if (rows === null) {
      return { reportName, rows: null, summaryPromise: null }
    }
    const summaryPromise = getReportSummary({ data: { reportName } })
    return { reportName, rows, summaryPromise }
  },
  component: ReportDetail
})
function ReportDetail() {
  const { reportName, rows, summaryPromise } = Route.useLoaderData()
  const { page, pageSize } = Route.useSearch()
  if (rows === null || rows === undefined) {
    return (
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{reportName}</h1>
        <Card className="mt-4">
          <CardContent className="text-sm text-muted-foreground">
            Todavia no se descargo ningun archivo de &quot;{reportName}&quot;.
            Dispara un refresh desde{' '}
            <Link to="/status" className="text-primary underline">
              /status
            </Link>
            .
          </CardContent>
        </Card>
      </div>
    )
  }
  const start = (page - 1) * pageSize
  const pageRows = rows.slice(start, start + pageSize)
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize))
  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">{reportName}</h1>
        {summaryPromise && (
          <Await
            promise={summaryPromise}
            fallback={
              <div className="flex gap-2">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-5 w-20 rounded-full" />
              </div>
            }
          >
            {summary =>
              summary && (
                <div className="flex gap-2">
                  <Badge variant="secondary">{summary.rowCount} filas</Badge>
                  <Badge variant="secondary">
                    {summary.columns.length} columnas
                  </Badge>
                </div>
              )
            }
          </Await>
        )}
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-sm text-muted-foreground">
            Pagina {page} de {totalPages}
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <Table>
            <TableBody>
              {pageRows.map((row, i) => (
                <TableRow key={i}>
                  <TableCell className="w-12 align-top text-muted-foreground">
                    {start + i + 1}
                  </TableCell>
                  <TableCell className="align-top">
                    <pre className="whitespace-pre-wrap text-xs">
                      {JSON.stringify(row)}
                    </pre>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="mt-4 flex items-center justify-center gap-2">
        <Link
          from={Route.fullPath}
          search={prev => ({ ...prev, page: Math.max(1, prev.page - 1) })}
          disabled={page <= 1}
          className={cn(
            buttonVariants({ variant: 'outline', size: 'icon-sm' }),
            page <= 1 && 'pointer-events-none opacity-50'
          )}
          aria-label="Pagina anterior"
        >
          <ChevronLeftIcon />
        </Link>
        <span className="text-sm text-muted-foreground">
          {page} / {totalPages}
        </span>
        <Link
          from={Route.fullPath}
          search={prev => ({
            ...prev,
            page: Math.min(totalPages, prev.page + 1)
          })}
          disabled={page >= totalPages}
          className={cn(
            buttonVariants({ variant: 'outline', size: 'icon-sm' }),
            page >= totalPages && 'pointer-events-none opacity-50'
          )}
          aria-label="Pagina siguiente"
        >
          <ChevronRightIcon />
        </Link>
      </div>
    </div>
  )
}
