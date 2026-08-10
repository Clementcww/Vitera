/* The mark.
 *
 * A V, and a description of how the product works.
 *
 * The descending stroke is broken into four segments: the days of an
 * admission, each one a separate run of the pipeline. They shorten as they
 * fall, because the repair window is closing. The ascending stroke is one
 * unbroken line that carries past the join and finishes higher than the
 * descent began, which is the claim recovered. Between them sits the catch.
 *
 * Read quickly it is a letter. Read slowly it is the detection curve, which is
 * the same shape the hero animates and the same shape the queue is ordered by.
 *
 * Drawn on a 24-unit grid. The segments are chunky enough to survive 17px in
 * the header and a photocopier at the bottom of an FPK; at very small sizes
 * they read as a dashed stroke, which is still the right story.
 */

const DESCENT = [
  // x1, y1, x2, y2: one segment per day of the stay.
  // Butt caps, not round: a round cap adds half the stroke width at each
  // end and closes the gap, which is how the days stopped being countable.
  [3.6, 3.6, 4.83, 5.66],
  [5.78, 7.25, 7.01, 9.31],
  [7.96, 10.9, 9.19, 12.96],
  [10.14, 14.55, 11.37, 16.61],
] as const

export function Logo({ size = 24, title }: { size?: number; title?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      role={title ? 'img' : 'presentation'}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {title && <title>{title}</title>}

      {/* the stay: one segment per day, the window narrowing */}
      {DESCENT.map(([x1, y1, x2, y2], i) => (
        <path
          key={i}
          d={`M${x1} ${y1} L${x2} ${y2}`}
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="butt"
          opacity={0.45 + i * 0.18}
        />
      ))}

      {/* the catch: where it stops falling */}
      <circle cx="11.9" cy="17.5" r="2.05" fill="currentColor" />

      {/* the recovery: unbroken, and it finishes higher than the fall began */}
      <path
        d="M13.5 15.9 L20.8 2.6"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function Wordmark({ size = 24 }: { size?: number }) {
  return (
    <span className="wordmark">
      <Logo size={size} title="Vitera" />
      <b>Vitera</b>
    </span>
  )
}
