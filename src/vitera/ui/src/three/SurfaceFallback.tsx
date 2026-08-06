import type { SurfaceCell } from '../types'
import { REMEDY_HEX } from './palette'
import { jt } from '../format'

/* The 2D reading of exactly the same matrix, in SVG.
 *
 * Not an apology screen. If the 3D view is unavailable this is what the judges
 * see, so it has to answer the same question on its own: for each episode, on
 * which day of stay did a finding first become visible, and what is it worth?
 *
 * SVG rather than canvas so it stays crisp on a projector and prints. */

export function SurfaceFallback({
  cells,
  maxDay,
  reason,
}: {
  cells: SurfaceCell[]
  maxDay: number
  reason?: string
}) {
  const episodes = [...new Set(cells.map((c) => c.e))].sort((a, b) => a - b)
  const cw = 26
  const ch = 15
  const padL = 96
  const padT = 28
  const w = padL + (maxDay + 1) * cw + 20
  const h = padT + episodes.length * ch + 34
  const byKey = new Map(cells.map((c) => [`${c.e}:${c.d}`, c]))
  const maxVal = Math.max(1, ...cells.map((c) => c.value_idr))

  return (
    <div className="fallback">
      {reason && (
        <p className="fbnote">
          Tampilan 3D tidak tersedia — {reason}. Data yang sama ditampilkan
          sebagai peta 2D.
        </p>
      )}
      <div className="scrollx">
        <svg width={w} height={h} role="img">
          {Array.from({ length: maxDay + 1 }, (_, d) => (
            <text
              key={d}
              x={padL + d * cw + cw / 2}
              y={padT - 10}
              textAnchor="middle"
              className="axis"
            >
              {d}
            </text>
          ))}
          <text x={padL} y={h - 10} className="axis">
            hari rawat →
          </text>

          {episodes.map((e, row) => {
            const label = cells.find((c) => c.e === e)?.episode_id ?? ''
            return (
              <g key={e}>
                <text
                  x={padL - 8}
                  y={padT + row * ch + 11}
                  textAnchor="end"
                  className="axis mono"
                >
                  {label}
                </text>
                {Array.from({ length: maxDay + 1 }, (_, d) => {
                  const c = byKey.get(`${e}:${d}`)
                  if (!c) return null
                  const active = c.flags > 0 && c.remedy
                  const fill = active
                    ? REMEDY_HEX[c.remedy!.toUpperCase() as keyof typeof REMEDY_HEX]
                    : '#e8e6dc'
                  const op = active ? 0.35 + 0.65 * (c.value_idr / maxVal) : 1
                  return (
                    <rect
                      key={d}
                      x={padL + d * cw + 1}
                      y={padT + row * ch + 1}
                      width={cw - 2}
                      height={ch - 3}
                      rx={2}
                      fill={fill}
                      fillOpacity={op}
                    >
                      <title>
                        {`${c.episode_id} · hari ${d} · ${c.flags} temuan` +
                          (c.value_idr ? ` · ${jt(c.value_idr)}` : '') +
                          (c.classes.length ? ` · ${c.classes.join(', ')}` : '')}
                      </title>
                    </rect>
                  )
                })}
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
