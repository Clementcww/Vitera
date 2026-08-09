import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import type { Group, Mesh } from 'three'
import type { SurfaceCell } from '../types'
import { BRAND, CLEAN_HEX, REMEDY_HEX } from './palette'

/* The hero animation.
 *
 * It animates the REAL detection surface — the same `surface.cells` the
 * Permukaan tab renders, which are real `run_pipeline` calls at each day of
 * each episode's stay. Nothing here is decorative geometry standing in for
 * data. That matters more than it sounds: a hero built from invented shapes
 * would be the one screen in this app that lies, and it would be the first
 * thing a judge sees.
 *
 * What it shows is the product's whole argument in one loop. A sweep line
 * advances along the day axis; a bar rises on the day its finding first became
 * detectable, and stays up. The forest that is standing well before the right
 * edge is the repair window — evidence sitting in the record for days before
 * anyone would have looked at it.
 *
 * Constraints inherited from Surface.tsx, for the same reasons: no 3D text
 * (troika fetches a font from a CDN and `make demo-offline` runs with the
 * network down), no shadows or post-processing (where an unfamiliar GPU dies).
 *
 * `prefers-reduced-motion` is honoured by rendering the finished state and not
 * animating at all — a looping sweep is exactly the kind of motion that makes
 * some people ill, and this is the first thing the app shows.
 */

type Tint = 'brand' | 'light'

const CELL = 0.9
const GAP = 0.1
/* The finished state is the one that reads, so it holds for longer than the
 * sweep takes. A loop that spends most of its time mid-build means a judge
 * glancing at the screen sees a half-drawn chart, or worse, an empty one. */
const DAYS_PER_SECOND = 3.0
const HOLD_SECONDS = 5.0

function Bars({
  cells,
  maxDay,
  maxVal,
  animate,
  tint,
}: {
  cells: SurfaceCell[]
  maxDay: number
  maxVal: number
  animate: boolean
  tint: Tint
}) {
  const refs = useRef<(Mesh | null)[]>([])

  const bars = useMemo(
    () =>
      cells.map((c) => {
        const active = c.flags > 0 && c.remedy
        const v = c.value_idr / maxVal
        // On the accent card the remedy palette would be orange-on-orange
        // and read as nothing at all, so the scene switches to white at
        // varying opacity: value becomes weight rather than hue. Remedy is
        // still legible everywhere it decides something (queue, flags, the
        // Permukaan tab); here the bar is showing magnitude over time.
        const light = tint === 'light'
        return {
          day: c.d,
          e: c.e,
          height: active ? 0.35 + 6.5 * v : 0.06,
          color: light
            ? '#ffffff'
            : active
              ? REMEDY_HEX[c.remedy!.toUpperCase() as keyof typeof REMEDY_HEX]
              : CLEAN_HEX,
          opacity: light ? (active ? 0.5 + 0.45 * v : 0.16) : 1,
        }
      }),
    [cells, maxVal, tint],
  )

  useFrame(({ clock }) => {
    if (!animate) return
    const period = (maxDay + 1) / DAYS_PER_SECOND + HOLD_SECONDS
    const t = clock.elapsedTime % period
    const sweep = t * DAYS_PER_SECOND

    for (let i = 0; i < bars.length; i++) {
      const m = refs.current[i]
      const b = bars[i]
      if (!m || !b) continue
      // Ease in over roughly one day either side of the sweep line, so bars
      // grow rather than pop. Clamped, so a bar that has risen stays risen —
      // the finding does not go away when the day advances.
      const k = Math.min(1, Math.max(0, sweep - b.day + 1))
      const s = k * k * (3 - 2 * k) // smoothstep
      m.scale.y = Math.max(0.001, s)
      m.position.y = (b.height * m.scale.y) / 2
    }
  })

  return (
    <group>
      {bars.map((b, i) => (
        <mesh
          key={i}
          ref={(el) => {
            refs.current[i] = el
          }}
          position={[b.day * (CELL + GAP), b.height / 2, b.e * (CELL + GAP)]}
          scale-y={animate ? 0.001 : 1}
        >
          <boxGeometry args={[CELL, b.height, CELL]} />
          <meshLambertMaterial
            color={b.color}
            transparent={b.opacity < 1}
            opacity={b.opacity}
          />
        </mesh>
      ))}
    </group>
  )
}

function Orbit({ children, animate }: { children: React.ReactNode; animate: boolean }) {
  const g = useRef<Group>(null)
  useFrame(({ clock }) => {
    if (!animate || !g.current) return
    // Very slow, and small amplitude. A hero that spins is a hero nobody can
    // read the label on.
    g.current.rotation.y = Math.sin(clock.elapsedTime * 0.06) * 0.16
  })
  return <group ref={g}>{children}</group>
}

export default function HeroScene({
  cells,
  maxDay,
  reducedMotion,
  tint = 'brand',
}: {
  cells: SurfaceCell[]
  maxDay: number
  reducedMotion: boolean
  tint?: Tint
}) {
  const nEp = useMemo(() => new Set(cells.map((c) => c.e)).size, [cells])
  const maxVal = useMemo(
    () => Math.max(1, ...cells.map((c) => c.value_idr)),
    [cells],
  )
  const animate = !reducedMotion

  const spanX = (maxDay + 1) * (CELL + GAP)
  const spanZ = nEp * (CELL + GAP)
  const centre: [number, number, number] = [spanX / 2, 0, spanZ / 2]

  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [spanX * 2.1, spanZ * 0.40, spanZ * 0.98], fov: 32 }}
      /* `pointerEvents: none` — the canvas sits behind the headline and the
         call to action, and must never swallow a click meant for either. */
      style={{ background: 'transparent', pointerEvents: 'none' }}
    >
      <ambientLight intensity={1.4} />
      <directionalLight position={[spanX, spanZ, spanZ]} intensity={1.05} />
      <Orbit animate={animate}>
        <group position={[-centre[0], 0, -centre[2]]}>
          <gridHelper
            args={[
              Math.max(spanX, spanZ) * 1.1,
              18,
              tint === 'light' ? '#f6c4b1' : BRAND.line,
              tint === 'light' ? '#e79a7c' : BRAND.line,
            ]}
            position={centre}
          />
          <Bars
            cells={cells}
            maxDay={maxDay}
            maxVal={maxVal}
            animate={animate}
            tint={tint}
          />
        </group>
      </Orbit>
    </Canvas>
  )
}
