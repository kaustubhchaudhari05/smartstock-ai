/**
 * Display formatting only. Values are computed by the backend; these helpers never do
 * business arithmetic, they only turn API values into text.
 */

/** Currency used for display (user decision). The backend stores plain decimals without a currency. */
export const CURRENCY = 'INR'
/** Indian English: ₹ symbol and lakh/crore digit grouping (1,00,000). */
export const LOCALE = 'en-IN'

const moneyFormat = new Intl.NumberFormat(LOCALE, { style: 'currency', currency: CURRENCY })
const numberFormat = new Intl.NumberFormat(LOCALE)
const dateTimeFormat = new Intl.DateTimeFormat(LOCALE, { dateStyle: 'medium', timeStyle: 'short' })
const relativeFormat = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })

/** "12098.75" -> "₹12,098.75"; "1234567.5" -> "₹12,34,567.50" */
export function formatMoney(value: string | number): string {
  return moneyFormat.format(Number(value))
}

export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

/** "3 days ago", "in 2 hours", "now" */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000)
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relativeFormat.format(Math.round(seconds / size), unit)
  }
  return relativeFormat.format(0, 'second')
}

/** "LOW_STOCK" -> "Low stock" */
export function humanize(value: string): string {
  const text = value.toLowerCase().replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}
