import type { AgentLimit, BenchmarkCaseResult } from '#/server/schemas'

export type AgentBenchmarkDatum = {
  agente: string
  casesWithResponseTime: number
  avgFirstResponseSeconds: number | null
  casesAnalyzed: number
  qualityOkCount: number
  qualityFailCount: number
  qualityOkPct: number | null
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

type AgentAccumulator = {
  responseTotal: number
  responseCount: number
  qualityOk: number
  qualityFail: number
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
      qualityOk: 0,
      qualityFail: 0,
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
    if (row.quality_ok !== null) {
      if (row.quality_ok) current.qualityOk += 1
      else current.qualityFail += 1
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
      const casesAnalyzed = stats.qualityOk + stats.qualityFail
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
        qualityOkCount: stats.qualityOk,
        qualityFailCount: stats.qualityFail,
        qualityOkPct:
          casesAnalyzed > 0 ? (stats.qualityOk / casesAnalyzed) * 100 : null,
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
  const withQuality = agents.filter(a => a.qualityOkPct !== null)
  if (withQuality.length === 0) return null
  return withQuality.reduce((best, current) =>
    (current.qualityOkPct ?? 0) > (best.qualityOkPct ?? 0) ? current : best
  )
}
