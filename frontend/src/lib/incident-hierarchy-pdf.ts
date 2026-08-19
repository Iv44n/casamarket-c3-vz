import type { jsPDF } from 'jspdf'
import { formatSecondsAsDuration } from '#/lib/duration'
import type {
  IncidentHierarchyNode,
  IncidentTicketExport
} from '#/lib/incident-analytics'
import type { IncidentCategory } from '#/server/schemas'

const PAGE_MARGIN_PX = 14
const PAGE_BOTTOM_MARGIN_PX = 16
const LINE_HEIGHT_PX = 6
const TICKET_LINE_HEIGHT_PX = 5
const INDENT_PX = 6
const MAX_LABEL_CHARS = 90
const SWATCH_SIZE_PX = 3

// RGB, resolved from this app's own --color-chart-1..4 tokens (light mode) --
// jsPDF can't read CSS custom properties or oklch(), so the resolved values are
// baked in here (see INCIDENT_CATEGORY_COLOR in incident-analytics.ts for the
// on-screen equivalent).
const INCIDENT_CATEGORY_PDF_COLOR: Record<
  IncidentCategory,
  [number, number, number]
> = {
  origen: [234, 79, 101],
  tipo: [0, 182, 137],
  ambito: [76, 148, 236],
  resultado: [216, 171, 0]
}
const TEXT_COLOR: [number, number, number] = [23, 23, 23]
const MUTED_COLOR: [number, number, number] = [110, 110, 110]

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function ensureSpace(
  doc: jsPDF,
  cursor: { y: number },
  lineHeight: number
): void {
  const pageHeight = doc.internal.pageSize.getHeight()
  if (cursor.y + lineHeight > pageHeight - PAGE_BOTTOM_MARGIN_PX) {
    doc.addPage()
    cursor.y = PAGE_MARGIN_PX
  }
}

function renderTicket(
  doc: jsPDF,
  ticket: IncidentTicketExport,
  x: number,
  cursor: { y: number }
): void {
  doc.setFontSize(8)
  doc.setFont('helvetica', 'normal')
  doc.setTextColor(MUTED_COLOR[0], MUTED_COLOR[1], MUTED_COLOR[2])
  const closed = ticket.horaFinal
    ? ` -- cerrado ${ticket.fechaFinal} ${ticket.horaFinal}`
    : ''
  const tiempo =
    ticket.tiempoSegundos === null
      ? ''
      : ` (${formatSecondsAsDuration(ticket.tiempoSegundos)})`
  const line = `- ${ticket.descripcion || 'Sin descripción'} -- ${ticket.agente || 'Sin agente'}${tiempo}${closed}`
  const maxWidth = doc.internal.pageSize.getWidth() - x - PAGE_MARGIN_PX
  const wrappedLines: string[] = doc.splitTextToSize(line, maxWidth)
  for (const wrappedLine of wrappedLines) {
    ensureSpace(doc, cursor, TICKET_LINE_HEIGHT_PX)
    doc.text(wrappedLine, x, cursor.y)
    cursor.y += TICKET_LINE_HEIGHT_PX
  }
}

function renderNode(
  doc: jsPDF,
  node: IncidentHierarchyNode,
  chain: IncidentCategory[],
  depth: number,
  cursor: { y: number }
): void {
  const x = PAGE_MARGIN_PX + depth * INDENT_PX
  ensureSpace(doc, cursor, LINE_HEIGHT_PX)
  const color = INCIDENT_CATEGORY_PDF_COLOR[chain[depth]]
  doc.setFillColor(color[0], color[1], color[2])
  doc.rect(x, cursor.y - SWATCH_SIZE_PX, SWATCH_SIZE_PX, SWATCH_SIZE_PX, 'F')
  doc.setFontSize(depth === 0 ? 12 : 10)
  doc.setFont('helvetica', depth === 0 ? 'bold' : 'normal')
  doc.setTextColor(TEXT_COLOR[0], TEXT_COLOR[1], TEXT_COLOR[2])
  doc.text(
    `${truncate(node.label, MAX_LABEL_CHARS - depth * INDENT_PX)} - ${node.count}`,
    x + SWATCH_SIZE_PX + 2,
    cursor.y
  )
  cursor.y += LINE_HEIGHT_PX
  for (const child of node.children ?? []) {
    renderNode(doc, child, chain, depth + 1, cursor)
  }
  for (const ticket of node.tickets ?? []) {
    renderTicket(doc, ticket, x + SWATCH_SIZE_PX + 2, cursor)
  }
}

export async function buildIncidentHierarchyPdf({
  title,
  subtitle,
  chain,
  tree
}: {
  title: string
  subtitle: string
  chain: IncidentCategory[]
  tree: IncidentHierarchyNode[]
}): Promise<Blob> {
  const { jsPDF: JsPdf } = await import('jspdf')
  const doc = new JsPdf()
  const cursor = { y: PAGE_MARGIN_PX }

  doc.setFontSize(16)
  doc.setFont('helvetica', 'bold')
  doc.setTextColor(TEXT_COLOR[0], TEXT_COLOR[1], TEXT_COLOR[2])
  doc.text(title, PAGE_MARGIN_PX, cursor.y)
  cursor.y += 8

  doc.setFontSize(10)
  doc.setFont('helvetica', 'normal')
  doc.setTextColor(MUTED_COLOR[0], MUTED_COLOR[1], MUTED_COLOR[2])
  const subtitleLines = doc.splitTextToSize(subtitle, 180)
  doc.text(subtitleLines, PAGE_MARGIN_PX, cursor.y)
  cursor.y += subtitleLines.length * 5 + 5

  for (const node of tree) {
    renderNode(doc, node, chain, 0, cursor)
  }

  return doc.output('blob')
}
