import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
export function tintChartColor(colorVar: string): string {
  return `color-mix(in oklab, ${colorVar} 55%, white 45%)`
}
export function sequentialChartMix(colorVar: string, percent: number): string {
  return `color-mix(in oklab, ${colorVar} ${percent}%, transparent)`
}
export function tintChartBackground(colorVar: string): string {
  return sequentialChartMix(colorVar, 8)
}
// TanStack Router's navigate() defaults resetScroll to true, so every filter change
// (a same-route search-only navigate) yanks the scroll back to the top. Wraps a route's
// navigate to default it to false instead, still overridable per call. The `any` here
// is what lets this wrap ANY route's differently-shaped, generic navigate() without
// losing its exact overloads -- the `as T` cast below restores the original type for
// callers, so every existing call site stays fully type-checked.
// biome-ignore lint/suspicious/noExplicitAny: see comment above
export function withoutScrollReset<T extends (opts: any) => any>(
  navigate: T
): T {
  return ((opts: Parameters<T>[0]) =>
    navigate({ resetScroll: false, ...opts })) as T
}
