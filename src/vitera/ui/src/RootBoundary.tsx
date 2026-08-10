import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

/* The last net under the whole app.
 *
 * `Boundary` in Hero.tsx fences each 3D scene, which is the right place for a
 * scene that fails on an unfamiliar GPU. It does not cover everything: an error
 * thrown while a boundary is ITSELF being unmounted propagates past it, and
 * opening the accent card unmounts one scene and mounts another in the same
 * commit. With nothing above, React unmounts the root and the screen goes
 * white — the exact "fails on stage" outcome the WebGL probe exists to avoid,
 * arriving by a different door.
 *
 * So: never a blank page. The reader gets the app's own words, and the error
 * text is ON SCREEN rather than only in a console nobody has open during a
 * demo. Reload is one button away and loses nothing, since every view is
 * derived from the payload files.
 */

export class RootBoundary extends Component<
  { children: ReactNode },
  { err: Error | null }
> {
  state: { err: Error | null } = { err: null }

  static getDerivedStateFromError(err: Error) {
    return { err }
  }

  componentDidCatch(err: Error, info: ErrorInfo) {
    // Keep the stack somewhere a developer can still reach it.
    console.error('Vitera: uncaught render error', err, info.componentStack)
  }

  render() {
    if (!this.state.err) return this.props.children
    return (
      <div className="rootfail">
        <h1>Tampilan ini gagal dimuat</h1>
        <p>
          Bagian lain aplikasi tidak terpengaruh. Muat ulang halaman untuk
          kembali. Tidak ada data yang hilang: setiap layar dihitung ulang dari
          berkas keluaran pipeline.
        </p>
        <button onClick={() => location.reload()}>Muat ulang</button>
        <pre>{this.state.err.message}</pre>
      </div>
    )
  }
}
