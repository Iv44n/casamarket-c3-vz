import type { AgentLimit, BenchmarkCaseResult } from '#/server/schemas'

// "ownConductOk*" recalcula el mismo AND-logic que el backend usa para quality_ok
// (greeting_level != 'ninguno' AND has_farewell AND handled_well_for_complexity AND
// spelling_ok), pero SIN informed_transfer -- row.quality_ok si lo incluye cuando
// had_transfer=true, y ese criterio depende de OTRO agente (quien transfirio el caso), no
// del agente final que lo cerro. Sin esto, un agente que solo recibe casos transferidos
// (p.ej. CARLOS GABRIEL HUAMAN MENDOZA) puede terminar con 0% de "calidad" pese a saludar y
// despedirse siempre, arrastrado por que quien le transfiere nunca avisa al cliente --
// bug real reportado por el usuario, confirmado y con fix acordado con backend.
export type AgentBenchmarkDatum = {
  agente: string
  casesWithResponseTime: number
  avgFirstResponseSeconds: number | null
  casesAnalyzed: number
  ownConductOkCount: number
  ownConductFailCount: number
  ownConductOkPct: number | null
  greetingCheckedCount: number
  greetingOkPct: number | null
  farewellCheckedCount: number
  farewellOkPct: number | null
  spellingCheckedCount: number
  spellingOkPct: number | null
  handledWellCheckedCount: number
  handledWellPct: number | null
  complexityCheckedCount: number
  complexityLowPct: number | null
  complexityMediumPct: number | null
  complexityHighPct: number | null
}

function agenteKeyOf(value: string | null): string {
  return value && value.trim() !== '' ? value : 'Sin agente'
}

function greetingOkOf(
  greetingLevel: BenchmarkCaseResult['greeting_level']
): boolean | null {
  return greetingLevel !== null
    ? greetingLevel === 'casual' || greetingLevel === 'formal'
    : null
}

// Mismo AND-logic que app/extraction/store.py usa para quality_ok, minus
// informed_transfer -- ver el comentario en AgentBenchmarkDatum arriba.
function ownConductOkOf(row: BenchmarkCaseResult): boolean | null {
  const criteria = [
    greetingOkOf(row.greeting_level),
    row.has_farewell,
    row.handled_well_for_complexity,
    row.spelling_ok
  ]
  return criteria.every(c => c !== null)
    ? criteria.every(c => c === true)
    : null
}

type AgentAccumulator = {
  responseTotal: number
  responseCount: number
  ownConductOk: number
  ownConductFail: number
  greetingOk: number
  greetingFail: number
  farewellOk: number
  farewellFail: number
  spellingOk: number
  spellingFail: number
  handledWellOk: number
  handledWellFail: number
  complexityLow: number
  complexityMedium: number
  complexityHigh: number
}

export function buildAgentBenchmarkRanking(
  results: BenchmarkCaseResult[],
  limit: AgentLimit
): AgentBenchmarkDatum[] {
  const byAgent = new Map<string, AgentAccumulator>()
  for (const row of results) {
    const agente = agenteKeyOf(row.agente)
    const current: AgentAccumulator = byAgent.get(agente) ?? {
      responseTotal: 0,
      responseCount: 0,
      ownConductOk: 0,
      ownConductFail: 0,
      greetingOk: 0,
      greetingFail: 0,
      farewellOk: 0,
      farewellFail: 0,
      spellingOk: 0,
      spellingFail: 0,
      handledWellOk: 0,
      handledWellFail: 0,
      complexityLow: 0,
      complexityMedium: 0,
      complexityHigh: 0
    }
    if (row.first_response_seconds !== null) {
      current.responseTotal += row.first_response_seconds
      current.responseCount += 1
    }
    const ownConductOk = ownConductOkOf(row)
    if (ownConductOk !== null) {
      if (ownConductOk) current.ownConductOk += 1
      else current.ownConductFail += 1
    }
    // ownConductOkPct es un AND de 4 criterios -- si UNO falla sistematicamente (p.ej.
    // un agente cuya campana nunca cierra con despedida) el score combinado colapsa a
    // ~0% aunque el resto este casi perfecto, sin decir cual de los 4 es el problema.
    // greetingOkPct/farewellOkPct exponen esos dos criterios sueltos (spelling/handled-well
    // ya los tenian) para poder diagnosticar en vez de ver un 0% parejo.
    const greetingOk = greetingOkOf(row.greeting_level)
    if (greetingOk !== null) {
      if (greetingOk) current.greetingOk += 1
      else current.greetingFail += 1
    }
    if (row.has_farewell !== null) {
      if (row.has_farewell) current.farewellOk += 1
      else current.farewellFail += 1
    }
    if (row.spelling_ok !== null) {
      if (row.spelling_ok) current.spellingOk += 1
      else current.spellingFail += 1
    }
    if (row.handled_well_for_complexity !== null) {
      if (row.handled_well_for_complexity) current.handledWellOk += 1
      else current.handledWellFail += 1
    }
    if (row.complexity === 'baja') current.complexityLow += 1
    else if (row.complexity === 'media') current.complexityMedium += 1
    else if (row.complexity === 'alta') current.complexityHigh += 1
    byAgent.set(agente, current)
  }
  const ranked = [...byAgent.entries()]
    .map(([agente, stats]) => {
      const casesAnalyzed = stats.ownConductOk + stats.ownConductFail
      const greetingCheckedCount = stats.greetingOk + stats.greetingFail
      const farewellCheckedCount = stats.farewellOk + stats.farewellFail
      const spellingCheckedCount = stats.spellingOk + stats.spellingFail
      const handledWellCheckedCount =
        stats.handledWellOk + stats.handledWellFail
      const complexityCheckedCount =
        stats.complexityLow + stats.complexityMedium + stats.complexityHigh
      return {
        agente,
        casesWithResponseTime: stats.responseCount,
        avgFirstResponseSeconds:
          stats.responseCount > 0
            ? stats.responseTotal / stats.responseCount
            : null,
        casesAnalyzed,
        ownConductOkCount: stats.ownConductOk,
        ownConductFailCount: stats.ownConductFail,
        ownConductOkPct:
          casesAnalyzed > 0 ? (stats.ownConductOk / casesAnalyzed) * 100 : null,
        greetingCheckedCount,
        greetingOkPct:
          greetingCheckedCount > 0
            ? (stats.greetingOk / greetingCheckedCount) * 100
            : null,
        farewellCheckedCount,
        farewellOkPct:
          farewellCheckedCount > 0
            ? (stats.farewellOk / farewellCheckedCount) * 100
            : null,
        spellingCheckedCount,
        spellingOkPct:
          spellingCheckedCount > 0
            ? (stats.spellingOk / spellingCheckedCount) * 100
            : null,
        handledWellCheckedCount,
        handledWellPct:
          handledWellCheckedCount > 0
            ? (stats.handledWellOk / handledWellCheckedCount) * 100
            : null,
        complexityCheckedCount,
        complexityLowPct:
          complexityCheckedCount > 0
            ? (stats.complexityLow / complexityCheckedCount) * 100
            : null,
        complexityMediumPct:
          complexityCheckedCount > 0
            ? (stats.complexityMedium / complexityCheckedCount) * 100
            : null,
        complexityHighPct:
          complexityCheckedCount > 0
            ? (stats.complexityHigh / complexityCheckedCount) * 100
            : null
      }
    })
    .sort(
      (a, b) =>
        b.casesWithResponseTime +
        b.casesAnalyzed -
        (a.casesWithResponseTime + a.casesAnalyzed)
    )
  return limit === 'all' ? ranked : ranked.slice(0, limit)
}

export function benchmarkTotals(results: BenchmarkCaseResult[]): {
  total: number
  analyzed: number
  qualityOkPct: number | null
  avgFirstResponseSeconds: number | null
} {
  const analyzedRows = results.filter(row => row.quality_ok !== null)
  const qualityOk = analyzedRows.filter(row => row.quality_ok).length
  const responseTimes = results
    .map(row => row.first_response_seconds)
    .filter((value): value is number => value !== null)
  return {
    total: results.length,
    analyzed: analyzedRows.length,
    qualityOkPct:
      analyzedRows.length > 0 ? (qualityOk / analyzedRows.length) * 100 : null,
    avgFirstResponseSeconds:
      responseTimes.length > 0
        ? responseTimes.reduce((sum, value) => sum + value, 0) /
          responseTimes.length
        : null
  }
}

export function bestQualityAgent(
  agents: AgentBenchmarkDatum[]
): AgentBenchmarkDatum | null {
  const withQuality = agents.filter(a => a.ownConductOkPct !== null)
  if (withQuality.length === 0) return null
  return withQuality.reduce((best, current) =>
    (current.ownConductOkPct ?? 0) > (best.ownConductOkPct ?? 0)
      ? current
      : best
  )
}

export type TransferNotificationDatum = {
  agente: string
  transferredCasesCount: number
  informedCount: number
  notInformedCount: number
  informedPct: number | null
}

// Agrupado por el agente de ORIGEN (el ultimo hop de transferred_from_agents, el
// predecesor inmediato de quien cerro el caso) -- no por row.agente. Muestra que tan
// seguido cada agente avisa al cliente ANTES de transferirle el caso a otro, algo que
// hoy queda invisible dentro de la calidad del agente que RECIBE la transferencia (ver
// el comentario en AgentBenchmarkDatum). Casos sin cadena registrada (transferred_from_agents
// vacio -- filas de antes de que el backend empezara a trackear esto) se excluyen, no se
// puede atribuir un origen.
export function buildTransferNotificationRanking(
  results: BenchmarkCaseResult[],
  limit: AgentLimit
): TransferNotificationDatum[] {
  const byAgent = new Map<
    string,
    { informed: number; notInformed: number; total: number }
  >()
  for (const row of results) {
    if (!row.had_transfer || row.transferred_from_agents.length === 0) {
      continue
    }
    const origin = agenteKeyOf(
      row.transferred_from_agents[row.transferred_from_agents.length - 1]
    )
    const current = byAgent.get(origin) ?? {
      informed: 0,
      notInformed: 0,
      total: 0
    }
    current.total += 1
    if (row.informed_transfer === true) current.informed += 1
    else if (row.informed_transfer === false) current.notInformed += 1
    byAgent.set(origin, current)
  }
  const ranked = [...byAgent.entries()]
    .map(([agente, stats]) => {
      const known = stats.informed + stats.notInformed
      return {
        agente,
        transferredCasesCount: stats.total,
        informedCount: stats.informed,
        notInformedCount: stats.notInformed,
        informedPct: known > 0 ? (stats.informed / known) * 100 : null
      }
    })
    .sort((a, b) => b.transferredCasesCount - a.transferredCasesCount)
  return limit === 'all' ? ranked : ranked.slice(0, limit)
}
