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
const AgentScene = lazy(() => import('../three/AgentScene'))

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
  onSurface,
  paused,
}: {
  payload: Payload
  sweep?: SweepPayload | null
  onEnter: () => void
  /** Reported upward so the headline card can drop its WebGL context while
   *  this card covers it. Nothing else reads it. */
  onSurface: (open: boolean) => void
  /** True while something covers the headline card. Same reason. */
  paused: boolean
}) {
  const [open, setOpen] = useState(false)
  const setSurface = (v: boolean) => {
    setOpen(v)
    onSurface(v)
  }
  const capability = useMemo(() => webglAvailable(), [])
  /* Read once, at mount. The card has no spare column on a narrow screen, so
     the scene is not drawn there at all; the matching CSS rule covers a window
     that is resized down afterwards. */
  const narrow = useMemo(
    () =>
      typeof matchMedia === 'function' && matchMedia('(max-width: 900px)').matches,
    [],
  )
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
        {/* Ambient, not data: see the header of AgentScene.tsx. Masked away
            from the left of the card in CSS so it never runs under the
            headline, and unmounted rather than hidden whenever another card
            covers this one, so only one WebGL context is ever alive. */}
        <div className="mainbg" aria-hidden="true">
          {capability.ok && !paused && !narrow && (
            <Boundary>
              <Suspense fallback={null}>
                <AgentScene reducedMotion={reducedMotion} tint="ink" />
              </Suspense>
            </Boundary>
          )}
        </div>

        {m?.n_episodes != null && (
          <span className="badge">
            Diukur pada {m.n_episodes} episode uji
            <i aria-hidden="true">→</i>
          </span>
        )}
        <h1>Vitera</h1>
        <p className="sub prose">
          Kami uji klaim sebelum BPJS melakukannya.
        </p>
        {/* The landing's one door, moved here from the accent card: this is
            the headline card, so this is where a first click belongs. */}
        <button className="solid" onClick={onEnter}>
          Buka antrean pagi <span aria-hidden="true">→</span>
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
            as a measured result, which it is not, and `results/` never
            computes one from here. */}
        <p className="mainnote">{payload.generated.cohort_caveat}</p>
      </section>

      <section
        className={'card card-accent' + (open ? ' open' : '')}
        onClick={() => !open && setSurface(true)}
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
                setSurface(false)
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

        {/* The card's own door is gone; the button now lives on the headline
            card. What is left is the prompt for the OTHER way in: clicking
            this card opens the surface and the unit's numbers, rather than
            the queue. */}
        {!open && (
          <div className="accentcta">
            <span className="accenthint">
              Klik kartu ini untuk inti sistemnya
              <span aria-hidden="true"> →</span>
            </span>
          </div>
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
