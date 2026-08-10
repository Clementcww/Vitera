import { Component, Suspense, lazy, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Payload, SweepPayload } from '../types'
import { webglAvailable } from '../three/webgl'
import { jt } from '../format'
import { Dashboard } from './Dashboard'

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
  sweep,
  onEnter,
}: {
  payload: Payload
  sweep?: SweepPayload | null
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
            Diukur pada {m.n_episodes} episode uji
            <i aria-hidden="true">→</i>
          </span>
        )}
        <h1>
          Kami uji klaim
          <br />
          sebelum BPJS melakukannya
        </h1>
        <p className="sub prose">
          Selagi pasien masih dirawat dan catatannya masih bisa diperbaiki.
        </p>
        <button className="solid" onClick={onEnter}>
          Buka antrean pagi
        </button>

        <div className="mainfoot">
          <div>
            <b className="mono">{episodes}</b>
            <span>episode</span>
          </div>
          <div>
            <b className="mono">{findings}</b>
            <span>temuan</span>
          </div>
          <div>
            <b className="mono">{recoverable ? jt(recoverable) : '·'}</b>
            <span>dapat dipulihkan</span>
          </div>
        </div>
        {/* These three figures describe the demo cohort, which is stratified
            so every defect class appears. Unlabelled, the rupiah figure reads
            as a measured result — which it is not, and `results/` never
            computes one from here. */}
        <p className="mainnote">{payload.generated.cohort_caveat}</p>
      </section>

      <section
        className={'card card-accent' + (open ? ' open' : '')}
        onClick={() => !open && setOpen(true)}
      >
        <div className="cardhd">
          <h2>
            Kapan tiap
            <br />
            klaim tertangkap
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
            {m.lead_time_median_days} hari lebih awal
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

        {/* Open, the card is the dashboard.
          *
          * The three floating figures that used to sit here said less than the
          * surface behind them already did, and the unit summary said the rest
          * on a screen of its own. They are one thing: the bars are the runs,
          * the numbers are what the runs found. Scrolling happens inside this
          * layer so the 3D stays put behind it and the reader keeps the shape
          * in view while reading the totals. */}
        {open && (
          <div className="dashwrap" onClick={(e) => e.stopPropagation()}>
            {/* The surface owns the top of the card and is left clear; the
                numbers begin below it, on a scrim, so nothing is read across a
                bar. Scroll them up and the shape stays behind. */}
            <div className="dashsheet">
              <p className="wnote">
                {payload.surface.cells.length} pemeriksaan harian. Satu batang
                di belakang, satu kali pipeline.
              </p>
              <Dashboard payload={payload} sweep={sweep} variant="surface" />
            </div>
          </div>
        )}
      </section>
    </>
  )
}
