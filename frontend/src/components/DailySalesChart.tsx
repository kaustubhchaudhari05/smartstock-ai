import { useState } from 'react'
import type { DailySales } from '../types/sales'
import { formatNumber } from '../utils/format'

interface DailySalesChartProps {
  data: DailySales[]
  /** Accessible description, e.g. "Units sold per day, last 30 days". */
  label: string
}

// Geometry (viewBox units; the SVG scales to its container width).
const W = 720
const H = 220
const M = { top: 12, right: 8, bottom: 26, left: 40 }
const INNER_W = W - M.left - M.right
const INNER_H = H - M.top - M.bottom
const MAX_BAR = 24 // marks spec: columns at most 24px thick
const GAP = 2 // surface gap between adjacent columns
const RADIUS = 4 // rounded data-end, square at the baseline

const dayLabel = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const fullDay = new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })
const parseDay = (iso: string) => new Date(`${iso}T00:00:00Z`)

/** Axis ticks at a clean step (1, 2, 5 x 10^n), at most ~4 intervals. Display only. */
function niceTicks(max: number): number[] {
  if (max <= 0) return [0, 1]
  const rough = max / 4
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? 10 * magnitude
  const ticks = []
  for (let v = 0; v <= max + step * 0.999; v += step) ticks.push(Math.round(v))
  return ticks
}

/** Column with a rounded top and a square base, from the baseline up to `y`. */
function columnPath(x: number, y: number, width: number, baseline: number): string {
  const r = Math.min(RADIUS, width / 2, baseline - y)
  return `M${x},${baseline} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${baseline} Z`
}

/** Units sold per UTC day (single series). The last day is today and still in progress. */
export default function DailySalesChart({ data, label }: DailySalesChartProps) {
  const [hover, setHover] = useState<number | null>(null)
  const [showTable, setShowTable] = useState(false)

  const ticks = niceTicks(Math.max(0, ...data.map((d) => d.units_sold)))
  const top = ticks[ticks.length - 1]
  const band = INNER_W / Math.max(data.length, 1)
  const barW = Math.min(MAX_BAR, band - GAP)
  const yOf = (v: number) => M.top + INNER_H - (v / top) * INNER_H
  const baseline = M.top + INNER_H
  const lastIndex = data.length - 1
  const labelEvery = Math.ceil(data.length / 6)
  const hovered = hover !== null ? data[hover] : undefined

  return (
    <div>
      <div className="position-relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-100 h-auto d-block daily-chart" role="img" aria-label={label}
          onMouseLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={yOf(t)} y2={yOf(t)} className="chart-grid" />
              <text x={M.left - 6} y={yOf(t)} dy="0.32em" textAnchor="end" className="chart-axis">
                {formatNumber(t)}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = M.left + i * band + (band - barW) / 2
            const today = i === lastIndex
            return (
              <g key={d.date}>
                {d.units_sold > 0 && (
                  <path d={columnPath(x, yOf(d.units_sold), barW, baseline)}
                    className={`chart-bar ${today ? 'is-partial' : ''} ${hover === i ? 'is-hover' : ''}`} />
                )}
                {/* Hit target: the whole band, taller than the mark. */}
                <rect x={M.left + i * band} y={M.top} width={band} height={INNER_H} fill="transparent"
                  onMouseEnter={() => setHover(i)} />
                {(i % labelEvery === 0 || today) && (
                  <text x={M.left + i * band + band / 2} y={H - 8} textAnchor="middle" className="chart-axis">
                    {today ? 'Today' : dayLabel.format(parseDay(d.date))}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
        {hovered && hover !== null && (
          <div className="chart-tooltip card shadow-sm small px-2 py-1"
            style={{ left: `${((M.left + hover * band + band / 2) / W) * 100}%` }} role="status">
            <div className="text-body-secondary">
              {fullDay.format(parseDay(hovered.date))}
              {hover === lastIndex && ' (so far)'}
            </div>
            <div className="fw-semibold">{formatNumber(hovered.units_sold)} units</div>
          </div>
        )}
      </div>
      <div className="d-flex justify-content-between align-items-center mt-1">
        <span className="small text-body-secondary">UTC days · today is still in progress</span>
        <button type="button" className="btn btn-link btn-sm p-0" onClick={() => setShowTable((v) => !v)}
          aria-expanded={showTable}>
          {showTable ? 'Hide table' : 'Show as table'}
        </button>
      </div>
      {showTable && (
        <div className="table-responsive mt-2" style={{ maxHeight: 240 }}>
          <table className="table table-sm mb-0">
            <caption className="visually-hidden">{label}</caption>
            <thead>
              <tr>
                <th scope="col">Day (UTC)</th>
                <th scope="col" className="text-end">Units sold</th>
              </tr>
            </thead>
            <tbody>
              {[...data].reverse().map((d, i) => (
                <tr key={d.date}>
                  <td>{fullDay.format(parseDay(d.date))}{i === 0 && ' (so far)'}</td>
                  <td className="text-end tabular-nums">{formatNumber(d.units_sold)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
