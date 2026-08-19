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
