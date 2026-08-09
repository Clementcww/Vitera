/* Three chart primitives, drawn as inline SVG.
 *
 * No charting library. The same reasoning as the BM25 in `models/bm25.py`: what
 * is needed here is forty lines of arithmetic, and a dependency inside a
 * reproducibility claim costs more than it saves.
 *
 * Colour follows the ENTITY, never its rank or its size. A remedy keeps the hue
 * it has in the queue, so a koder who learned that orange means the doctor does
 * not have to learn it twice. The three hues are validated against the panel
 * surface — lightness band, chroma floor, CVD separation, normal-vision
 * separation and contrast all pass — which is why `--obtain` and `--recode` are
 * a step more saturated than they were.
 *
 * Every chart carries its numbers in a `<title>` (native tooltip, works with no
 * JavaScript and with a screen reader) and the caller keeps a collapsed table,
 * so nothing is gated behind colour or behind a hover.
 */

const AXIS = 'rgba(20, 20, 19, .16)'

export interface Slice {
  key: string
  label: string
  value: number
  color: string
  note?: string
}

/* Horizontal bars — magnitude across a few named categories.
 *
 * Horizontal because the category names are phrases ("Petugas berkas, masih
 * bisa setelah pulang"), and a column chart would either clip them or turn them
 * on their side. Values ride the bar tips; the axis is not drawn, because with
 * three labelled bars it would carry nothing the labels do not. */
export function BarRows({ data, max }: { data: Slice[]; max?: number }) {
  const top = max ?? Math.max(1, ...data.map((d) => d.value))
  return (
    <div className="chart-rows">
      {data.map((d) => (
        <div className="crow" key={d.key}>
          <span className="clabel">
            <i className="cdot" style={{ background: d.color }} />
            {d.label}
          </span>
          <span className="ctrack">
            <span
              className="cbar"
              style={{ width: `${(d.value / top) * 100}%`, background: d.color }}
            >
              <title>{`${d.label}: ${d.value}`}</title>
            </span>
            <b className="cval">{d.value}</b>
          </span>
          {d.note && <span className="cnote">{d.note}</span>}
        </div>
      ))}
    </div>
  )
}

/* One stacked bar — part of a whole, when the parts have long names.
 *
 * Not a pie: the segments here are close in size and a reader would have to
 * compare angles. Segments are separated by a 2px gap in the surface colour
 * rather than by a stroke, so the separation costs no ink. */
export function StackedBar({ data }: { data: Slice[] }) {
  const total = Math.max(1, data.reduce((n, d) => n + d.value, 0))
  const shown = data.filter((d) => d.value > 0)
  return (
    <div className="chart-stack">
      <div className="sbar">
        {shown.map((d) => (
          <span
            key={d.key}
            className="sseg"
            style={{ width: `${(d.value / total) * 100}%`, background: d.color }}
          >
            <title>{`${d.label}: ${d.value} dari ${total}`}</title>
          </span>
        ))}
      </div>
      <div className="slegend">
        {shown.map((d) => (
          <span key={d.key}>
            <i className="cdot" style={{ background: d.color }} />
            {d.label} <b>{d.value}</b>
          </span>
        ))}
      </div>
    </div>
  )
}

export interface Point {
  x: number
  y: number
}

/* An area over day of stay — the shape the whole product argues for.
 *
 * One series, so no legend: the caption says what is plotted. The area is the
 * hue at a wash rather than a block, the line is 2px, and only the marked day
 * is labelled — a number on every point would be unreadable and unread. */
export function AreaTrend({
  points,
  markX,
  color,
  height = 116,
}: {
  points: Point[]
  markX?: number | null
  color: string
  height?: number
}) {
  const W = 320
  const H = height
  const PAD_B = 6
  const maxY = Math.max(1, ...points.map((p) => p.y))
  const maxX = Math.max(1, ...points.map((p) => p.x))
  const sx = (x: number) => (x / maxX) * (W - 8) + 4
  const sy = (y: number) => H - PAD_B - (y / maxY) * (H - PAD_B - 8)

  const line = points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(' ')
  const area = `${sx(points[0]?.x ?? 0)},${H - PAD_B} ${line} ${sx(
    points[points.length - 1]?.x ?? 0,
  )},${H - PAD_B}`

  return (
    <svg
      className="chart-area"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Temuan menurut hari rawat"
    >
      <line x1="4" y1={H - PAD_B} x2={W - 4} y2={H - PAD_B} stroke={AXIS} strokeWidth="1" />
      <polygon points={area} fill={color} opacity="0.14" />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {markX != null && (
        <g>
          <line
            x1={sx(markX)}
            y1="6"
            x2={sx(markX)}
            y2={H - PAD_B}
            stroke={color}
            strokeWidth="1"
            strokeDasharray="3 3"
            opacity=".7"
          />
          <circle cx={sx(markX)} cy={sy(points[markX]?.y ?? 0)} r="4.5" fill={color} />
        </g>
      )}
      {points.map((p) => (
        <rect
          key={p.x}
          x={sx(p.x) - 6}
          y="0"
          width="12"
          height={H - PAD_B}
          fill="transparent"
        >
          <title>{`Hari ${p.x}: ${p.y} temuan`}</title>
        </rect>
      ))}
    </svg>
  )
}

/** The axis labels, as HTML. See the note on `.cticks`. */
export function TrendTicks({
  maxDay,
  markLabel,
}: {
  maxDay: number
  markLabel?: string
}) {
  return (
    <div className="cticks">
      <span>hari 0</span>
      {markLabel && <span className="mid">{markLabel}</span>}
      <span>hari {maxDay}</span>
    </div>
  )
}
