import { Component, Suspense, lazy, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { SurfaceCell } from '../types'
import { SurfaceFallback } from './SurfaceFallback'
import { webglAvailable } from './webgl'

/* The 3D view's containment.
 *
 * three.js is the one dependency in this app that can take the demo down on an
 * unknown machine, so it is fenced three ways and never reached by default:
 *
 *   1. lazy import  — the workbench parses and renders before the three.js
 *                     chunk is even fetched. A failure here cannot delay the
 *                     screen the demo actually depends on.
 *   2. capability probe — checked before the import is triggered, so an
 *                     unsupported machine never downloads or executes it.
 *   3. error boundary — anything that still throws at runtime (driver reset,
 *                     context loss) swaps to the 2D view instead of blanking
 *                     the app.
 *
 * All three paths land on the same 2D matrix, which carries the same
 * information. If this whole view were cut, nothing else in the app changes —
 * which is the property that made it safe to build at all.
 */

const Surface = lazy(() => import('./Surface'))

class Boundary extends Component<
  { fallback: (reason: string) => ReactNode; children: ReactNode },
  { error: string | null }
> {
  state = { error: null as string | null }

  static getDerivedStateFromError(e: unknown) {
    return { error: e instanceof Error ? e.message : String(e) }
  }

  render() {
    return this.state.error
      ? this.props.fallback(this.state.error)
      : this.props.children
  }
}

export function SurfaceView({
  cells,
  maxDay,
}: {
  cells: SurfaceCell[]
  maxDay: number
}) {
  const capability = useMemo(() => webglAvailable(), [])
  const [force2d, setForce2d] = useState(false)
  const use3d = capability.ok && !force2d

  return (
    <section className="view">
      <h1>Permukaan deteksi</h1>
      <p className="lede">
        Satu batang = satu kali pipeline dijalankan pada hari tersebut. Baca
        mendatar untuk melihat hari temuan mulai terdeteksi; tinggi batang
        adalah nilai yang dapat dipulihkan menurut grouper. Ini bukan diff —
        diff, urutan dan penekanan adalah tugas sweep.
      </p>

      <div className="switch">
        <button
          className={'f' + (use3d ? ' on' : '')}
          onClick={() => setForce2d(false)}
          disabled={!capability.ok}
          title={capability.ok ? undefined : capability.reason}
        >
          3D
        </button>
        <button
          className={'f' + (!use3d ? ' on' : '')}
          onClick={() => setForce2d(true)}
        >
          2D
        </button>
        {!capability.ok && <span className="swnote">{capability.reason}</span>}
      </div>

      {use3d ? (
        <Boundary
          fallback={(reason) => (
            <SurfaceFallback cells={cells} maxDay={maxDay} reason={reason} />
          )}
        >
          <Suspense fallback={<div className="loading">memuat tampilan 3D…</div>}>
            <Surface cells={cells} maxDay={maxDay} />
          </Suspense>
        </Boundary>
      ) : (
        <SurfaceFallback cells={cells} maxDay={maxDay} reason={capability.reason} />
      )}
    </section>
  )
}
