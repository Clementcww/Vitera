import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import type { Group, Mesh, MeshBasicMaterial } from 'three'
import { BRAND } from './palette'

/* The headline card's scene: the agent, watching a patient who is still
 * admitted.
 *
 * Read the honesty rule before changing this. `HeroScene` animates REAL
 * `run_pipeline` output and must keep doing so, because it sits on the card
 * that makes a measured claim. This one is ambient by design: a heartbeat
 * trace, an agent core beating in time with it, and two rings of attention. It
 * is not data and is never labelled as data.
 *
 * It shares a card with the three figures in `.mainfoot`, which is exactly the
 * arrangement that could mislead, so: it carries no axis, no scale and no
 * label, and it is masked out of the half of the card the text occupies.
 * Nothing on this card should ever read as a chart of those numbers. Do not
 * put a figure on it, and do not reuse it on a card that quotes a result.
 *
 * What it is trying to say is the one thing the About block is for: the agent
 * is running WHILE the signal is still arriving, not after the patient has gone
 * home. So the trace travels, and the core pulses on the same clock.
 *
 * Same constraints as HeroScene, for the same reasons:
 *   - no 3D text (troika fetches a font from a CDN; `make demo-offline` runs
 *     with the network down),
 *   - no shadows and no post-processing (that is where an unfamiliar GPU on a
 *     borrowed laptop dies, and criterion 8 does not care whose GPU it was),
 *   - `prefers-reduced-motion` renders the resting state and never starts a
 *     frame loop, because this is a looping animation on a landing page.
 */

/* Which way round the marks go. `ink` draws dark marks for a light card,
 * `light` draws pale ones for the ink card. Two palettes rather than one with
 * opacity turned down, because a pale wireframe on white is invisible and a
 * dark one on ink is a hole. */
type Tint = 'ink' | 'light'

const INK: Record<Tint, { mesh: string; ring: string; node: string }> = {
  ink: { mesh: BRAND.dark, ring: BRAND.mid, node: BRAND.dark },
  light: { mesh: BRAND.light, ring: BRAND.light, node: BRAND.light },
}
const MESH_ALPHA: Record<Tint, number> = { ink: 0.17, light: 0.45 }
const RING_ALPHA: Record<Tint, number> = { ink: 0.45, light: 0.28 }
const NODE_ALPHA: Record<Tint, number> = { ink: 0.5, light: 0.9 }
const TRACE_FLOOR: Record<Tint, number> = { ink: 0.1, light: 0.18 }
const TRACE_RANGE: Record<Tint, number> = { ink: 0.62, light: 0.72 }

/* One beat, sampled. Deliberately crude: it is a motif, not an ECG, and
 * nothing downstream reads it. */
const BEAT = [
  0.05, 0.05, 0.06, 0.1, 0.16, 0.1, 0.06, 0.05, 0.05, 0.14, 0.55, 1.0, 0.3,
  0.05, 0.05, 0.09, 0.2, 0.28, 0.18, 0.08, 0.05, 0.05,
]
const BARS = 34
const SPAN = 5.4
const BAR_W = 0.075
const TRACE_Y = -1.35
const AMP = 1.5
const SAMPLES_PER_SECOND = 9

/** Height of the trace at continuous sample position `p`, wrapped and eased. */
function beatAt(p: number): number {
  const i = Math.floor(p)
  const f = p - i
  const n = BEAT.length
  const a = BEAT[((i % n) + n) % n] ?? 0
  const b = BEAT[(((i + 1) % n) + n) % n] ?? 0
  return a + (b - a) * f
}

function Trace({ animate, tint }: { animate: boolean; tint: Tint }) {
  const refs = useRef<(Mesh | null)[]>([])
  const step = SPAN / (BARS - 1)
  const floor = TRACE_FLOOR[tint]
  const range = TRACE_RANGE[tint]

  useFrame(({ clock }) => {
    if (!animate) return
    const offset = clock.elapsedTime * SAMPLES_PER_SECOND
    for (let i = 0; i < BARS; i++) {
      const m = refs.current[i]
      if (!m) continue
      const v = beatAt(i + offset)
      const h = Math.max(0.001, v * AMP)
      m.scale.y = h
      m.position.y = TRACE_Y + h / 2
      // The QRS spike is the only part of the trace that should draw the eye.
      // Opacity carries that rather than a second colour, so the card keeps one
      // accent and the spike reads as the same mark, brighter.
      ;(m.material as MeshBasicMaterial).opacity = floor + range * v
    }
  })

  return (
    <group>
      {Array.from({ length: BARS }, (_, i) => {
        const rest = beatAt(i) * AMP
        return (
          <mesh
            key={i}
            ref={(el) => {
              refs.current[i] = el
            }}
            position={[-SPAN / 2 + i * step, TRACE_Y + rest / 2, 0]}
            scale-y={rest}
          >
            <boxGeometry args={[BAR_W, 1, BAR_W]} />
            <meshBasicMaterial
              color={BRAND.orange}
              transparent
              opacity={floor + range * beatAt(i)}
            />
          </mesh>
        )
      })}
    </group>
  )
}

/** A ring of attention with one node travelling it. Echoes the CSS rings the
 *  card already has, so the 2D fallback and the 3D scene are the same motif. */
function Ring({
  radius,
  tilt,
  speed,
  phase,
  animate,
  tint,
}: {
  radius: number
  tilt: number
  speed: number
  phase: number
  animate: boolean
  tint: Tint
}) {
  const node = useRef<Group>(null)

  useFrame(({ clock }) => {
    if (!animate || !node.current) return
    node.current.rotation.z = phase + clock.elapsedTime * speed
  })

  return (
    <group rotation={[tilt, 0, 0]}>
      <mesh>
        <torusGeometry args={[radius, 0.008, 8, 96]} />
        <meshBasicMaterial
          color={INK[tint].ring}
          transparent
          opacity={RING_ALPHA[tint]}
        />
      </mesh>
      <group ref={node} rotation={[0, 0, phase]}>
        <mesh position={[radius, 0, 0]}>
          <sphereGeometry args={[0.055, 14, 14]} />
          <meshBasicMaterial
            color={INK[tint].node}
            transparent
            opacity={NODE_ALPHA[tint]}
          />
        </mesh>
      </group>
    </group>
  )
}

/** The agent. Beats on the same clock as the trace, because that is the point:
 *  it is reading the signal as the signal arrives. */
function Core({ animate, tint }: { animate: boolean; tint: Tint }) {
  const shell = useRef<Mesh>(null)
  const heart = useRef<Mesh>(null)

  useFrame(({ clock }) => {
    if (!animate) return
    const t = clock.elapsedTime
    const v = beatAt(BEAT.length - 11 + t * SAMPLES_PER_SECOND)
    if (shell.current) {
      shell.current.rotation.y = t * 0.22
      shell.current.rotation.x = Math.sin(t * 0.35) * 0.18
      const s = 1 + 0.06 * v
      shell.current.scale.setScalar(s)
    }
    if (heart.current) heart.current.scale.setScalar(0.9 + 0.35 * v)
  })

  return (
    <group>
      <mesh ref={shell}>
        <icosahedronGeometry args={[0.95, 1]} />
        <meshBasicMaterial
          color={INK[tint].mesh}
          wireframe
          transparent
          opacity={MESH_ALPHA[tint]}
        />
      </mesh>
      <mesh ref={heart}>
        <sphereGeometry args={[0.3, 24, 24]} />
        <meshBasicMaterial color={BRAND.orange} />
      </mesh>
    </group>
  )
}

export default function AgentScene({
  reducedMotion,
  tint = 'ink',
}: {
  reducedMotion: boolean
  tint?: Tint
}) {
  const animate = !reducedMotion
  const rings = useMemo(
    () => [
      { radius: 1.65, tilt: 1.25, speed: 0.45, phase: 0 },
      { radius: 2.25, tilt: 1.05, speed: -0.3, phase: 2.1 },
    ],
    [],
  )

  return (
    <Canvas
      dpr={[1, 2]}
      camera={{ position: [0, 0.9, 8.4], fov: 34 }}
      /* Behind the About copy, and it must never swallow a click meant for the
         card underneath it. */
      style={{ background: 'transparent', pointerEvents: 'none' }}
    >
      {/* Centred: the canvas now spans the full card, and the headline lives
          below this scene rather than beside it, so nothing is dodging text
          on either side. */}
      <group position={[0, 0.75, 0]} scale={0.78}>
        <Core animate={animate} tint={tint} />
        {rings.map((r, i) => (
          <Ring key={i} {...r} animate={animate} tint={tint} />
        ))}
        <Trace animate={animate} tint={tint} />
      </group>
    </Canvas>
  )
}
