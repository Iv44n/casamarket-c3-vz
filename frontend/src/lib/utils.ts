import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
export function tintChartColor(colorVar: string): string {
  return `color-mix(in oklab, ${colorVar} 55%, white 45%)`
}
export function tintChartBackground(colorVar: string): string {
  return `color-mix(in oklab, ${colorVar} 8%, transparent)`
}
