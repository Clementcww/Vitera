import { Component, Suspense, lazy, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Payload } from '../types'
import { webglAvailable } from '../three/webgl'
import { jt } from '../format'

/* The two cards that are only the landing: the headline, and the accent card
 * carrying the detection surface.
 *
 * The third card is not here. That one is the hinge between landing and
 * workbench and lives in App, because it has to survive the mode change as the
 * same element in order to morph rather than be replaced.
 *
 * The accent card has its own smaller morph: clicking it expands it over the
 * bento and starts the 3D scene, which is where the day-of-stay surface lives
 * now that it is no longer a page of its own. It is the same data the
 * pipeline produced, one bar per run_pipeline call per day of stay.
 *
 * Fenced as ever: lazy chunk, WebGL probe, error boundary, and the canvas only
 * mounts once the card is open, so a closed landing never touches WebGL.
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

export function HeroCards({
  payload,
  onEnter,
}: {
  payload: Payload
  onEnter: () => void
}) {
  const [open, setOpen] = useState(false)
  const capability = useMemo(() => webglAvailable(), [])
  const reducedMotion = useMemo(
    () =>
      typeof matchMedia === 'function' &&
      matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )

  const episodes = payload.episodes.length
  const findings = payload.episodes.reduce((n, e) => n + e.flags.length, 0)
  const recoverable = payload.episodes.reduce(
    (n, e) => n + (e.money.delta_idr ?? 0),
    0,
  )
  const m = payload.measured

  return (
    <>
      <section className="card card-main">
        {m?.n_episodes != null && (
          <span className="badge">
            Measured on {m.n_episodes} held-out episodes
            <i aria-hidden="true">→</i>
          </span>
        )}
        <h1>
          We find what BPJS
          <br />
          would find
        </h1>
        <p className="sub prose">
          While the patient is still on the ward and the record can still be
          put right.
        </p>
        <button className="solid" onClick={onEnter}>
          Open this morning&rsquo;s queue
        </button>

        <div className="mainfoot">
          <div>
            <b className="mono">{episodes}</b>
            <span>episodes</span>
          </div>
          <div>
            <b className="mono">{findings}</b>
            <span>findings</span>
          </div>
          <div>
            <b className="mono">{recoverable ? jt(recoverable) : '·'}</b>
            <span>recoverable</span>
          </div>
        </div>
      </section>

      <section
        className={'card card-accent' + (open ? ' open' : '')}
        onClick={() => !open && setOpen(true)}
      >
        <div className="cardhd">
          <h2>
            When each
            <br />
            claim was caught
          </h2>
          {open && (
            <button
              className="closebtn"
              onClick={(e) => {
                e.stopPropagation()
                setOpen(false)
              }}
              aria-label="Tutup"
            >
              ×
            </button>
          )}
        </div>

        {m?.lead_time_median_days != null && (
          <span className="chip yellow">
            {m.lead_time_median_days} days earlier
          </span>
        )}

        <div className="cardbg">
          {capability.ok && open && (
            <Boundary>
              <Suspense fallback={null}>
                <HeroScene
                  cells={payload.surface.cells}
                  maxDay={payload.surface.max_day}
                  reducedMotion={reducedMotion}
                  tint="light"
                />
              </Suspense>
            </Boundary>
          )}
        </div>

        {open && (
          <div className="widgets">
            <div className="w w1">
              <span>Found before discharge</span>
              <b className="mono">
                {m ? Math.round(m.detection_rate * 100) : '·'}%
              </b>
            </div>
            <div className="w w2">
              <span>Two days or more to act</span>
              <b className="mono">
                {m?.lead_time_share_ge_2_days != null
                  ? Math.round(m.lead_time_share_ge_2_days * 100)
                  : '·'}
                %
              </b>
            </div>
            <div className="w w3">
              <span>Checked every day</span>
              <b className="mono">{payload.surface.cells.length}</b>
            </div>
            <p className="wnote">
              One bar is one run of the pipeline on that day of the stay.
              Bar height is what the grouper says is recoverable.
            </p>
          </div>
        )}
      </section>
    </>
  )
}
