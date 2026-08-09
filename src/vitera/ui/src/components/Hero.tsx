import { Component, Suspense, lazy, useMemo } from 'react'
import type { ReactNode } from 'react'
import type { Payload } from '../types'
import { webglAvailable } from '../three/webgl'
import { jt } from '../format'
import { Term } from './Term'

/* The opening frame.
 *
 * A koder opens this tool thirty to fifty times a day, so a hero that stands
 * between them and the queue every morning would be a defect, not a feature.
 * It is therefore an entry state: shown once on load, dismissed by the call to
 * action, and never shown again while the app stays open. `Lewati` skips it
 * outright for anyone who already knows what this is.
 *
 * Everything quantitative on it is read from the payload — episode count,
 * findings, recoverable value, the seed. No hero copy states a number that the
 * pipeline did not produce, and none of it is rounded up. The one-liner is the
 * project's own, and it is a claim about what the system does, not about what
 * it recovers.
 *
 * The 3D scene is fenced exactly as the Permukaan tab is: lazy chunk, WebGL
 * capability probe, error boundary. Every failure path renders the hero
 * without it, and the headline and call to action are plain DOM sitting above
 * the canvas — so a dead GPU costs the demo an animation, never an entrance.
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

  const episodes = payload.episodes.length
  const findings = payload.episodes.reduce((n, e) => n + e.flags.length, 0)
  const queries = payload.episodes.reduce(
    (n, e) => n + e.flags.filter((f) => f.remedy === 'QUERY').length,
    0,
  )
  const recoverable = payload.episodes.reduce(
    (n, e) => n + (e.money.delta_idr ?? 0),
    0,
  )
  // NOT "still admitted": every episode in the frozen corpus carries a
  // discharge_day, so that count is always zero and would read as the product
  // never catching anyone mid-stay. The honest concurrent number this corpus
  // can support is how many per-day pipeline runs stand behind the queue —
  // one per episode per day of stay.
  const dailyRuns = payload.surface.cells.length
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
          Setiap malam, selama pasien masih dirawat, sistem membaca ulang{' '}
          <Term k="rekam-medis">rekam medis</Term> dan menandai apa yang akan
          membuat <Term k="klaim">klaim</Term> rumah sakit ke{' '}
          <Term k="bpjs">BPJS</Term> tertunda — lalu menyerahkan daftar
          perbaikan kepada <Term k="koder">koder</Term>, selagi masih ada waktu
          memperbaikinya. Setiap temuan mengutip dokumen aslinya{' '}
          <Term k="verbatim">kata demi kata</Term>.
        </p>

        <ol className="herosteps">
          <li>
            <b>Pasien dirawat.</b> Catatan medis bertambah setiap hari — hasil
            laboratorium, obat, catatan dokter.
          </li>
          <li>
            <b>Sistem memeriksa setiap malam.</b> Bukti klinis sering muncul
            berhari-hari sebelum ditulis sebagai diagnosis. Jendela itulah yang
            diperiksa.
          </li>
          <li>
            <b>Manusia yang memutuskan.</b> Sistem hanya menyiapkan draf;
            koder dan dokter yang menindaklanjuti. Tidak ada yang dikirim
            otomatis.
          </li>
        </ol>

        <div className="herostats">
          <div>
            <b className="mono">{episodes}</b>
            <span>episode diperiksa</span>
          </div>
          <div>
            <b className="mono">{findings}</b>
            <span>temuan</span>
          </div>
          <div>
            <b className="mono">{queries}</b>
            <span>perlu DPJP</span>
          </div>
          <div>
            <b className="mono">{dailyRuns}</b>
            <span>pemeriksaan harian</span>
          </div>
          <div>
            <b className="mono">{recoverable ? jt(recoverable) : '—'}</b>
            <span>
              dapat dipulihkan · <Term k="grouper">grouper</Term>
            </span>
          </div>
          {measured?.lead_time_median_days != null && (
            <div className="measured" title={measured.source}>
              <b className="mono">{measured.lead_time_median_days} hari</b>
              <span>
                median temuan terdeteksi sebelum pasien pulang — diukur pada{' '}
                {measured.n_episodes} episode uji
              </span>
            </div>
          )}
        </div>

        <div className="heroacts">
          <button className="act primary" onClick={onEnter}>
            Buka antrean pagi
          </button>
          <button className="act" onClick={onSurface}>
            Lihat permukaan deteksi
          </button>
        </div>

        <p className="herofoot">
          Data sintetis, kohort demo terstratifikasi ·{' '}
          <span className="mono">seed {payload.generated.seed}</span>
          {payload.generated.advisory && ' · mode advisory: lapisan model mati'}
        </p>
      </div>
    </section>
  )
}
