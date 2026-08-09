import { Component, Suspense, lazy, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Payload } from '../types'
import { webglAvailable } from '../three/webgl'
import { jt } from '../format'

/* The opening frame: a bento of three cards on a warm grey page.
 *
 * The reference design's signature move is that a card is not a link, it is a
 * door: clicking one expands it to fill the frame and reveals the thing it was
 * summarising, with small outlined widgets floating over it. That works here
 * because both cards genuinely have something behind them, so the expansion
 * shows real state rather than a decorative interstitial.
 *
 * Copy is deliberately thin. The screen says what this is, shows two numbers
 * that came out of the pipeline, and offers two doors.
 *
 * The 3D scene is fenced as elsewhere: lazy chunk, WebGL probe, error
 * boundary. Everything that matters is plain DOM above the canvas.
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

type Card = 'surface' | 'queue' | null

export function Hero({
  payload,
  onEnter,
  onSurface,
}: {
  payload: Payload
  onEnter: () => void
  onSurface: () => void
}) {
  const [open, setOpen] = useState<Card>(null)
  const capability = useMemo(() => webglAvailable(), [])
  const reducedMotion = useMemo(
    () =>
      typeof matchMedia === 'function' &&
      matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )

  const episodes = payload.episodes.length
  const findings = payload.episodes.reduce((n, e) => n + e.flags.length, 0)
  const queries = payload.episodes.reduce(
    (n, e) => n + e.flags.filter((f) => f.remedy === 'QUERY').length,
    0,
  )
  const obtains = payload.episodes.reduce(
    (n, e) => n + e.flags.filter((f) => f.remedy === 'OBTAIN').length,
    0,
  )
  const recodes = payload.episodes.reduce(
    (n, e) => n + e.flags.filter((f) => f.remedy === 'RECODE').length,
    0,
  )
  const recoverable = payload.episodes.reduce(
    (n, e) => n + (e.money.delta_idr ?? 0),
    0,
  )
  const m = payload.measured

  return (
    <div className="stage">
      <header className="floathdr">
        <div className="hpill brandpill">
          <span className="dot" />
          Vitera
        </div>
        <nav className="hpill navpill">
          <button onClick={onEnter}>Antrean</button>
          <button onClick={onSurface}>Permukaan</button>
        </nav>
        <button className="hpill ctapill" onClick={onEnter}>
          Buka antrean <span aria-hidden="true">→</span>
        </button>
      </header>

      <div className={'bento' + (open ? ' has-open' : '')}>
        {/* ---- the headline card ---------------------------------------- */}
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
          <p className="sub prose">Selagi masih ada waktu memperbaikinya.</p>
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
        </section>

        {/* ---- the accent card: expands onto the detection surface ------- */}
        <section
          className={'card card-accent' + (open === 'surface' ? ' open' : '')}
          onClick={() => open !== 'surface' && setOpen('surface')}
        >
          <div className="cardhd">
            <h2>
              Permukaan
              <br />
              deteksi
            </h2>
            {open === 'surface' && (
              <button
                className="closebtn"
                onClick={(e) => {
                  e.stopPropagation()
                  setOpen(null)
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
            {capability.ok && open === 'surface' && (
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

          {open === 'surface' && (
            <div className="widgets">
              <div className="w w1">
                <span>Terdeteksi sebelum pulang</span>
                <b className="mono">
                  {m ? Math.round(m.detection_rate * 100) : '·'}%
                </b>
              </div>
              <div className="w w2">
                <span>Jendela perbaikan ≥ 2 hari</span>
                <b className="mono">
                  {m?.lead_time_share_ge_2_days != null
                    ? Math.round(m.lead_time_share_ge_2_days * 100)
                    : '·'}
                  %
                </b>
              </div>
              <div className="w w3">
                <span>Pemeriksaan harian</span>
                <b className="mono">{payload.surface.cells.length}</b>
              </div>
              <button
                className="ghost"
                onClick={(e) => {
                  e.stopPropagation()
                  onSurface()
                }}
              >
                Lihat selengkapnya
              </button>
            </div>
          )}
        </section>

        {/* ---- the dark card: expands onto the queue --------------------- */}
        <section
          className={'card card-dark' + (open === 'queue' ? ' open' : '')}
          onClick={() => open !== 'queue' && setOpen('queue')}
        >
          <div className="cardhd">
            <h2>
              Antrean
              <br />
              pagi
            </h2>
            {open === 'queue' && (
              <button
                className="closebtn"
                onClick={(e) => {
                  e.stopPropagation()
                  setOpen(null)
                }}
                aria-label="Tutup"
              >
                ×
              </button>
            )}
          </div>

          <div className="rings" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>

          <div className="remedies">
            <span className="rdot" style={{ background: 'var(--query)' }} />
            <span className="rdot" style={{ background: 'var(--obtain)' }} />
            <span className="rdot" style={{ background: 'var(--recode)' }} />
            <span className="chip outline">{findings} temuan</span>
          </div>

          {open === 'queue' && (
            <div className="orbitnodes" aria-hidden="true">
              <span className="n1">
                <i style={{ background: 'var(--query)' }} />
                DPJP
              </span>
              <span className="n2">
                <i style={{ background: 'var(--obtain)' }} />
                Petugas berkas
              </span>
              <span className="n3">
                <i style={{ background: 'var(--recode)' }} />
                Koder
              </span>
            </div>
          )}

          {open === 'queue' && (
            <div className="widgets">
              <div className="w w1">
                <span>Perlu dokter (DPJP)</span>
                <b className="mono">{queries}</b>
              </div>
              <div className="w w2">
                <span>Perlu petugas berkas</span>
                <b className="mono">{obtains}</b>
              </div>
              <div className="w w3">
                <span>Perlu koder</span>
                <b className="mono">{recodes}</b>
              </div>
              <button
                className="ghost"
                onClick={(e) => {
                  e.stopPropagation()
                  onEnter()
                }}
              >
                Buka antrean
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
