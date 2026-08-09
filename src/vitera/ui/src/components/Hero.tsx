import { Component, Suspense, lazy, useMemo } from 'react'
import type { ReactNode } from 'react'
import type { Payload } from '../types'
import { webglAvailable } from '../three/webgl'
import { jt } from '../format'

/* The opening frame.
 *
 * A koder opens this tool thirty times a day, so the hero is an entry state:
 * shown once on load, dismissed by either call to action, never returned to
 * while the app stays open.
 *
 * Deliberately sparse. The screen has one job, which is to say what this is
 * and then get out of the way. Every sentence not doing that work sits between
 * the reader and the queue, so the explanatory detail lives one click deeper,
 * in the queue's own first-time-reader panel.
 *
 * Numbers are read from the payload. The lead time is the measured headline
 * from the full held-out split and renders only when it exists.
 *
 * The 3D scene is fenced as the Permukaan tab is: lazy chunk, WebGL probe,
 * error boundary. Headline and buttons are plain DOM above the canvas, so a
 * dead GPU costs an animation, never the entrance.
 */

const HeroScene = lazy(() => import('../three/HeroScene'))

class Boundary extends Component<{ children: ReactNode }, { dead: boolean }> {
  state = { dead: false }
  static getDerivedStateFromError() {
    return { dead: true }
  }
  render() {
    return this.state.dead ? null : this.props.children
  }
}

export function Hero({
  payload,
  onEnter,
  onSurface,
}: {
  payload: Payload
  onEnter: () => void
  onSurface: () => void
}) {
  const capability = useMemo(() => webglAvailable(), [])
  const reducedMotion = useMemo(
    () =>
      typeof matchMedia === 'function' &&
      matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )

  const findings = payload.episodes.reduce((n, e) => n + e.flags.length, 0)
  const recoverable = payload.episodes.reduce(
    (n, e) => n + (e.money.delta_idr ?? 0),
    0,
  )
  const measured = payload.measured

  return (
    <section className="hero">
      <div className="herobg" aria-hidden="true">
        {capability.ok && (
          <Boundary>
            <Suspense fallback={null}>
              <HeroScene
                cells={payload.surface.cells}
                maxDay={payload.surface.max_day}
                reducedMotion={reducedMotion}
              />
            </Suspense>
          </Boundary>
        )}
      </div>

      <div className="herofg">
        <span className="eyebrow">Verifikasi klaim BPJS · rawat inap</span>
        <h1 className="herotitle">
          Kami uji klaim sebelum BPJS melakukannya,
          <br />
          selagi masih ada waktu memperbaikinya.
        </h1>
        <p className="herolede prose">
          Setiap malam, selama pasien masih dirawat.
        </p>

        <div className="herostats">
          {measured?.lead_time_median_days != null && (
            <div className="measured">
              <b className="mono">{measured.lead_time_median_days} hari</b>
              <span>lebih awal, median</span>
            </div>
          )}
          <div>
            <b className="mono">{findings}</b>
            <span>temuan</span>
          </div>
          <div>
            <b className="mono">{recoverable ? jt(recoverable) : '·'}</b>
            <span>dapat dipulihkan</span>
          </div>
        </div>

        <div className="heroacts">
          <button className="act primary" onClick={onEnter}>
            Buka antrean pagi
          </button>
          <button className="act" onClick={onSurface}>
            Permukaan deteksi
          </button>
        </div>
      </div>
    </section>
  )
}
