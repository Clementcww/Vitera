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
 * Every chart carries its numbers where a pointer can reach them, and the
 * caller keeps a collapsed table, so nothing is gated behind colour or hover.
 *
 * Note the two different mechanisms, which is not an inconsistency: inside an
 * `<svg>` a tooltip is a child `<title>` ELEMENT, and in HTML it is a `title`
 * ATTRIBUTE. Writing `<title>` inside an HTML `<span>` produces neither — the
 * parser treats it as the document's title element, so the tooltip silently
 * does not exist and the browser tab gets renamed to the last bar's label.
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
        <div className="crow" key={d.key} title={`${d.label}: ${d.value}`}>
          <span className="clabel">
            <i className="cdot" style={{ background: d.color }} />
            {d.label}
          </span>
          <span className="ctrack">
            <span
              className="cbar"
              style={{ width: `${(d.value / top) * 100}%`, background: d.color }}
            />
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
            title={`${d.label}: ${d.value} dari ${total}`}
            style={{ width: `${(d.value / total) * 100}%`, background: d.color }}
          />
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

/* An area over a single axis.
 *
 * One series, so no legend: the caption says what is plotted. The area is the
 * hue at a wash rather than a block, the line is 2px, and only the marked
 * point is labelled — a number on every point would be unreadable and unread.
 *
 * `yMax` pins the scale. Pass it whenever the reader is meant to judge the
 * height against something outside the data — a rate against 100%, a false
 * positive rate against its ceiling. Auto-scaling a rate makes 27% and 3% draw
 * the same shape, which is exactly the misreading `refLine` exists to prevent. */
export function AreaTrend({
  points,
  markX,
  color,
  height = 116,
  yMax,
  refLine,
  refLabel,
  unit = '',
}: {
  points: Point[]
  markX?: number | null
  color: string
  height?: number
  yMax?: number
  refLine?: number
  refLabel?: string
  unit?: string
}) {
  const W = 320
  const H = height
  const PAD_B = 6
  const maxY = yMax ?? Math.max(1, ...points.map((p) => p.y))
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
      {refLine != null && refLine <= maxY && (
        <g>
          <line
            x1="4"
            y1={sy(refLine)}
            x2={W - 4}
            y2={sy(refLine)}
            stroke={AXIS}
            strokeWidth="1"
            strokeDasharray="4 3"
          />
          {refLabel && (
            <text x={W - 6} y={sy(refLine) - 4} className="refl" textAnchor="end">
              {refLabel}
            </text>
          )}
        </g>
      )}
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
          <title>{`${p.x}: ${p.y}${unit}`}</title>
        </rect>
      ))}
    </svg>
  )
}

/* Vertical bars for a short ordered series — one per day of stay.
 *
 * Used where the reader compares adjacent values rather than reading a shape,
 * which is what a count per day is. Bars carry a 2px surface gap rather than a
 * stroke, so the separation costs no ink, and the largest bar is labelled
 * because it is the one the caption refers to. */
export function DayBars({
  values,
  color,
  height = 74,
}: {
  values: number[]
  color: string
  height?: number
}) {
  const max = Math.max(1, ...values)
  const peak = values.indexOf(max)
  return (
    <div className="daybars" style={{ height }}>
      {values.map((v, i) => (
        <span
          key={i}
          className={'dbar' + (i === peak ? ' peak' : '')}
          title={`Hari ${i}: ${v} temuan baru`}
        >
          <i style={{ height: `${(v / max) * 100}%`, background: color }} />
          {i === peak && <b>{v}</b>}
        </span>
      ))}
    </div>
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
