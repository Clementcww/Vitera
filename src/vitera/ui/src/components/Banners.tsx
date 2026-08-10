import type { Payload, SweepPayload } from '../types'
import { staleHours } from '../data'

/* Four pieces of chrome, each of which exists because of a rule that is easy
 * to satisfy badly.
 *
 * Advisory (rule 8): the system must remain useful with the model layer off.
 * The failure mode is not that it stops working — it is that a rules-only run
 * renders identically to a full one and the koder trusts a check that never
 * happened. So the banner names the classes that were NOT examined. "Degraded
 * mode" tells a koder nothing; "D2, D3, D4 and D7 were not checked tonight"
 * tells them exactly which claims still need a human.
 *
 * Staleness (sweep rule 5): a stale queue must never render as a fresh one.
 * `SweepStatus` shows the last SUCCESSFUL sweep, never the last attempted one,
 * and when no sweep output exists it says so rather than falling back to
 * anything. `StaleBanner` is the loud version, for when the last good sweep is
 * old enough that the queue in front of the koder is not this morning's.
 *
 * The pill this replaced showed the episode count and the random seed. A seed
 * is a reproducibility fact, not a freshness fact, and a queue with no clock on
 * it looks equally current whether it ran an hour ago or never. */

export function AdvisoryBanner({ payload }: { payload: Payload }) {
  const ep = payload.episodes.find((e) => e.advisory)
  if (!payload.generated.advisory && !ep) return null
  const unchecked = ep?.classes_unchecked ?? ['D2', 'D3', 'D4', 'D5', 'D7']

  return (
    <details className="banner b-adv" open>
      <summary>
        <span className="mark">~</span>
        Mode advisory: hanya aturan deterministik
        <span className="more">rincian</span>
      </summary>
      <div className="detail">
        Lapisan model tidak tersedia; pipeline tetap berjalan. Kelas{' '}
        <b>{unchecked.join(', ')} tidak diperiksa</b> pada proses ini. Antrean
        bersih tidak berarti klaim bersih.
        {payload.generated.model_unavailable && (
          <div className="why-mono">{payload.generated.model_unavailable}</div>
        )}
      </div>
    </details>
  )
}

/** Hours since the last successful sweep, above which the queue is called out
 *  as stale. A little over one night: a sweep that missed its 02:00 slot and
 *  has not run since is exactly the case this exists for. */
const STALE_AFTER_HOURS = 30

export function SweepStatus({
  sweep,
  payload,
}: {
  sweep: SweepPayload | null
  payload: Payload
}) {
  const n = payload.episodes.length

  if (!sweep) {
    return (
      <div className="hpill statpill nosweep" title="jalankan `make sweep-demo`">
        <span className="led off" />
        {n} episode · <b>belum ada sweep</b>
      </div>
    )
  }

  const stale = staleHours(sweep)
  const partial = sweep.status === 'partial'
  const old = stale !== null && stale > STALE_AFTER_HOURS
  const tone = partial || old ? ' warn' : ''

  return (
    <div
      className={'hpill statpill' + tone}
      title={
        sweep.generated.mode === 'replay'
          ? 'replay 7 malam dari korpus — tanggal sintetis, tidak membaca jam'
          : `selesai ${sweep.generated.finished_at}`
      }
    >
      <span className={'led' + (partial || old ? ' off' : '')} />
      {n} episode · sweep{' '}
      <b className="mono">{sweep.last_successful_sweep ?? '—'}</b>
      {partial && <span className="tag">sebagian</span>}
      {sweep.generated.mode === 'replay' && <span className="tag">replay</span>}
    </div>
  )
}

export function StaleBanner({ sweep }: { sweep: SweepPayload | null }) {
  if (!sweep) return null
  const stale = staleHours(sweep)
  const partial = sweep.status === 'partial'
  const old = stale !== null && stale > STALE_AFTER_HOURS
  if (!partial && !old) return null

  const attempted = sweep.last_attempted_sweep
  const succeeded = sweep.last_successful_sweep

  return (
    <details className="banner b-stale" open>
      <summary>
        <span className="mark">!</span>
        {partial
          ? 'Sweep terakhir tidak selesai — antrean ini belum lengkap'
          : `Antrean berumur ${Math.round(stale!)} jam`}
        <span className="more">rincian</span>
      </summary>
      <div className="detail">
        Sweep sukses terakhir <b>{succeeded ?? 'tidak ada'}</b>
        {attempted && attempted !== succeeded && (
          <>
            ; percobaan terakhir <b>{attempted}</b> berhenti sebelum kohortnya
            habis
          </>
        )}
        . Episode yang dilewati tidak muncul di daftar ini, jadi antrean yang
        pendek belum tentu berarti pekerjaan sedikit. Yang ditampilkan adalah
        proses <b>sukses</b> terakhir, bukan percobaan terakhir — antrean basi
        tidak boleh tampak segar.
        {sweep.nights.at(-1)?.skipped.length ? (
          <div className="why-mono">
            {sweep.nights.at(-1)!.skipped.length} episode dilewati:{' '}
            {sweep.nights
              .at(-1)!
              .skipped.slice(0, 3)
              .map((s) => `${s.episode_id} (${s.error})`)
              .join(' · ')}
          </div>
        ) : null}
        {sweep.nights.at(-1)?.ceiling_hit && (
          <div className="why-mono">
            batas biaya tercapai: {sweep.nights.at(-1)!.ceiling_hit}
          </div>
        )}
      </div>
    </details>
  )
}

export function DroppedSpanBanner({ dropped }: { dropped: number }) {
  if (!dropped) return null
  return (
    <details className="banner b-stale">
      <summary>
        <span className="mark">!</span>
        {dropped} temuan dibuang: kutipan tidak cocok dengan rekam medis
        <span className="more">rincian</span>
      </summary>
      <div className="detail">
        Setiap temuan harus menunjuk kutipan verbatim pada dokumen yang dirujuk
        (aturan arsitektur 6). Pemeriksaan diulang di sisi klien terhadap teks
        yang akan ditampilkan; yang gagal dibuang sebelum tampil, bukan
        ditampilkan dengan kutipan yang dilonggarkan.
      </div>
    </details>
  )
}
