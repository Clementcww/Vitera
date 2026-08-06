import { useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import type { SurfaceCell } from '../types'
import { BRAND, CLEAN_HEX, REMEDY_HEX } from './palette'
import { jt } from '../format'

/* The detection surface: episode × day of stay × recoverable value.
 *
 * This is the one view in Vitera with a genuine third dimension, and it exists
 * to make the concurrent thesis visible in a single frame. Read across a row
 * and you see the day a finding first became detectable; read the height and
 * you see what documenting it is worth. A bar that stands up on day 3 and is
 * still standing on day 8 is the product's whole argument — the evidence was
 * there for five days before anyone would have looked.
 *
 * Every bar is one `run_pipeline` call at that day. Not a diff: diffing,
 * ordering and suppression belong to the sweep in bucket 13, and doing them
 * here would be building the second system CLAUDE.md forbids.
 *
 * Two deliberate constraints:
 *
 * - **No 3D text.** drei's <Text> pulls a font through troika, which reaches
 *   for a CDN by default. `make demo-offline` has to run with the network
 *   down, so axis labels are HTML overlaid on the canvas instead — which also
 *   keeps them in Poppins and crisp on a projector.
 * - **No post-processing, no shadows.** Both are where an unfamiliar GPU
 *   drops to single figures. Flat lighting reads fine and always runs.
 */

const CELL = 1.0
const GAP = 0.12

function Bars({
  cells,
  maxVal,
  onHover,
}: {
  cells: SurfaceCell[]
  maxVal: number
  onHover: (c: SurfaceCell | null) => void
}) {
  return (
    <group>
      {cells.map((c) => {
        const active = c.flags > 0 && c.remedy
        // Height carries recoverable value; a finding with no tariff movement
        // still gets a floor so it is visible as a finding rather than absent.
        const v = c.value_idr / maxVal
        const height = active ? 0.3 + 7.5 * v : 0.05
        const color = active
          ? REMEDY_HEX[c.remedy!.toUpperCase() as keyof typeof REMEDY_HEX]
          : CLEAN_HEX
        return (
          <mesh
            key={`${c.e}:${c.d}`}
            position={[c.d * (CELL + GAP), height / 2, c.e * (CELL + GAP)]}
            onPointerOver={(e) => {
              e.stopPropagation()
              onHover(c)
            }}
            onPointerOut={() => onHover(null)}
          >
            <boxGeometry args={[CELL, height, CELL]} />
            <meshLambertMaterial color={color} />
          </mesh>
        )
      })}
    </group>
  )
}

export default function Surface({
  cells,
  maxDay,
}: {
  cells: SurfaceCell[]
  maxDay: number
}) {
  const [hover, setHover] = useState<SurfaceCell | null>(null)

  const nEp = useMemo(() => new Set(cells.map((c) => c.e)).size, [cells])
  const maxVal = useMemo(
    () => Math.max(1, ...cells.map((c) => c.value_idr)),
    [cells],
  )

  const spanX = (maxDay + 1) * (CELL + GAP)
  const spanZ = nEp * (CELL + GAP)
  const centre: [number, number, number] = [spanX / 2, 0, spanZ / 2]

  return (
    <div className="surfacewrap">
      <Canvas
        dpr={[1, 2]}
        /* Framed low and along the episode axis. A high three-quarter view
           flattens the bars, and bar height IS the recoverable value — the
           one quantity this view exists to show. */
        camera={{
          position: [spanX * 1.5, spanZ * 0.42, spanZ * 0.95],
          fov: 38,
        }}
        style={{ background: BRAND.light }}
      >
        <ambientLight intensity={1.35} />
        <directionalLight position={[spanX, spanZ, spanZ]} intensity={1.15} />
        <gridHelper
          args={[Math.max(spanX, spanZ) * 1.05, 20, BRAND.mid, BRAND.line]}
          position={centre}
        />
        <Bars cells={cells} maxVal={maxVal} onHover={setHover} />
        <OrbitControls
          target={centre}
          enableDamping
          dampingFactor={0.08}
          maxPolarAngle={Math.PI / 2.1}
        />
      </Canvas>

      {/* HTML overlay rather than 3D text — see the header comment. */}
      <div className="soverlay">
        <div className="slegend">
          {(['QUERY', 'OBTAIN', 'RECODE'] as const).map((k) => (
            <span key={k}>
              <i style={{ background: REMEDY_HEX[k] }} />
              {k[0] + k.slice(1).toLowerCase()}
            </span>
          ))}
          <span>
            <i style={{ background: CLEAN_HEX }} />
            tidak ada temuan
          </span>
        </div>
        <div className="saxes">
          sumbu X hari rawat · sumbu Z episode · tinggi nilai yang dapat
          dipulihkan (grouper)
        </div>
      </div>

      {hover && (
        <div className="stip">
          <b className="mono">{hover.episode_id}</b>
          <span>hari rawat ke-{hover.d}</span>
          <span>
            {hover.flags} temuan
            {hover.classes.length ? ` · ${hover.classes.join(', ')}` : ''}
          </span>
          <span className="mono">
            {hover.value_idr ? jt(hover.value_idr) : 'tarif tidak berubah'}
          </span>
        </div>
      )}
    </div>
  )
}
