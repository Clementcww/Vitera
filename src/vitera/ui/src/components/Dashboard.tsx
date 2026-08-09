import type { Payload, EpisodeView, Remedy } from '../types'
import { jt, REMEDY } from '../format'
import { Term } from './Term'

/* L2 — the unit view.
 *
 * Read by the kepala unit casemix, not by the koder. The question it answers
 * is not "which claim do I open next" but "is the unit on top of this month,
 * and what is about to become unrepairable".
 *
 * Two constraints shape it and neither is negotiable:
 *
 *   Unit aggregates only. There is no per-koder cut anywhere on this screen
 *   and there must never be one. A queue that doubles as a productivity
 *   monitor is a queue whose findings get closed rather than fixed.
 *
 *   Every rupiah comes from the grouper. An episode it could not group is
 *   counted as a case and excluded from the money, shown as its own figure so
 *   the exclusion is visible rather than silently rounded away.
 */

function windowState(e: EpisodeView): 'open' | 'closing' | 'closed' {
  if (e.still_admitted) return 'open'
  return e.discharge_day !== null ? 'closing' : 'closed'
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: string
  sub?: string
  tone?: 'query' | 'ok' | 'plain'
}) {
  return (
    <div className={'stat' + (tone && tone !== 'plain' ? ' t-' + tone : '')}>
      <span className="stat-label">{label}</span>
      <b className="stat-value">{value}</b>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  )
}

export function Dashboard({ payload }: { payload: Payload }) {
  const eps = payload.episodes
  const flagged = eps.filter((e) => e.verdict === 'flagged')
  const abstain = eps.filter((e) => e.verdict === 'abstain')

  const ungroupable = eps.filter((e) => e.money.now.ungroupable_reason !== null)
  const recoverable = eps.reduce((n, e) => n + (e.money.delta_idr ?? 0), 0)

  const flags = eps.flatMap((e) => e.flags)
  const byRemedy = (r: Remedy) => flags.filter((f) => f.remedy === r).length

  // Findings whose repair still needs the patient on the ward. This is the
  // number that decays overnight, so it leads.
  //
  // `admitted` counts every episode evaluated mid-stay, flagged or not, because
  // the lede is describing the ward and not the queue. `onWard` narrows to the
  // ones that actually have something to fix.
  const admitted = eps.filter((e) => windowState(e) === 'open')
  const onWard = flagged.filter((e) => windowState(e) === 'open')
  const onWardQueries = onWard
    .flatMap((e) => e.flags)
    .filter((f) => f.remedy === 'QUERY').length

  const m = payload.measured
  const llmCalls = eps.reduce((n, e) => n + e.trace.llm_calls, 0)
  const zeroLlm = eps.filter((e) => e.trace.llm_calls === 0).length

  return (
    <section className="view dash">
      <h1>Ringkasan unit</h1>
      <p className="lede">
        {payload.generated.cohort} episode rawat inap, {admitted.length} di
        antaranya masih dirawat pagi ini. Semua angka rupiah berasal dari
        grouper; episode yang tidak dapat dikelompokkan tetap dihitung sebagai
        kasus, tetapi tidak ikut dijumlahkan nilainya.
      </p>

      {payload.generated.advisory && (
        <p className="dash-warn">
          Proses terakhir berjalan tanpa lapisan model. Sebagian kelas temuan
          tidak diperiksa, jadi angka di bawah adalah batas bawah, bukan
          total.
        </p>
      )}

      <div className={'lead' + (onWardQueries ? ' urgent' : '')}>
        <b>{onWardQueries}</b>
        <div>
          <strong>perlu dokter selagi pasien masih di ruangan</strong>
          <span>
            {onWardQueries
              ? 'Jendela ini tertutup saat pasien pulang. Sisanya masih bisa besok.'
              : admitted.length
                ? 'Pagi ini tidak ada yang perlu dokter di ruangan.'
                : 'Tidak ada episode yang masih dirawat pada kohort ini, jadi tidak ada jendela perbaikan yang terbuka.'}
          </span>
        </div>
      </div>

      <div className="stats">
        <Stat
          label="Klaim dengan temuan"
          value={`${flagged.length} / ${eps.length}`}
          sub={abstain.length ? `${abstain.length} perlu penilaian koder` : undefined}
        />
        <Stat
          label="Dapat dipulihkan"
          value={jt(recoverable)}
          sub="selisih tarif, dari grouper"
        />
        <Stat
          label="Tidak dapat dikelompokkan"
          value={String(ungroupable.length)}
          sub={ungroupable.length ? 'tarif tidak diperkirakan' : 'tidak ada'}
        />
      </div>

      <h2 className="dash-h">Siapa yang harus bertindak</h2>
      <table className="dash-tbl">
        <thead>
          <tr>
            <th>Siapa</th>
            <th>Temuan</th>
            <th>Sisa waktu</th>
          </tr>
        </thead>
        <tbody>
          {(['QUERY', 'OBTAIN', 'RECODE'] as Remedy[]).map((r) => (
            <tr key={r}>
              <td>
                <span className="rdot" style={{ background: `var(--${REMEDY[r].css})` }} />
                {REMEDY[r].who}
              </td>
              <td className="num">{byRemedy(r)}</td>
              <td className="win">
                {r === 'QUERY'
                  ? 'sampai pasien pulang'
                  : r === 'OBTAIN'
                    ? 'sampai berkas dikirim'
                    : 'sampai klaim disubmit'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 className="dash-h">Deteksi</h2>
      {m ? (
        <div className="stats">
          <Stat
            label="Terdeteksi sebelum pulang"
            value={`${Math.round(m.detection_rate * 100)}%`}
            sub={`n = ${m.n_episodes}`}
          />
          <Stat
            label="Sedini ini ditemukan"
            value={m.lead_time_median_days !== null ? `${m.lead_time_median_days} hari` : '—'}
            sub="median, sebelum pasien pulang"
          />
          <Stat
            label="Jendela perbaikan ≥ 2 hari"
            value={
              m.lead_time_share_ge_2_days !== null
                ? `${Math.round(m.lead_time_share_ge_2_days * 100)}%`
                : '—'
            }
            sub="masih bisa diperbaiki"
          />
        </div>
      ) : (
        <p className="dash-empty">Belum diukur pada split uji.</p>
      )}

      {/* Precision matters here: `llm_calls` counts calls to the language
          model, which writes prose and decides nothing. Every episode was
          still scored by the cross-encoder, which is a model — so "no LLM
          call" is true and "deterministic rules alone" would not be. */}
      <p className="dash-cost">
        <span>{llmCalls}</span> panggilan model bahasa untuk seluruh kohort ·{' '}
        <span>{Math.round((zeroLlm / Math.max(1, eps.length)) * 100)}%</span>{' '}
        episode selesai tanpa satu pun panggilan model bahasa. Deteksi dikerjakan
        aturan dan <Term k="cross-encoder">cross-encoder</Term> yang berjalan di
        rumah sakit; model bahasa hanya menulis penjelasannya.
      </p>

      <p className="dash-foot">
        Tidak ada angka per koder di layar ini, dan tidak akan pernah ada.
        Antrean yang sekaligus menjadi penilaian kinerja adalah antrean yang
        ditutup, bukan dikerjakan.
      </p>
    </section>
  )
}
