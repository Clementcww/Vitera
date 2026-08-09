import type { Payload, EpisodeView, Remedy } from '../types'
import { jt, REMEDY } from '../format'
import { Term } from './Term'
import { AreaTrend, BarRows, StackedBar, TrendTicks } from './charts'

/* L2 — the unit view.
 *
 * Read by the kepala unit casemix, not by the koder. The question it answers
 * is not "which claim do I open next" but "is the unit on top of this month,
 * and what is about to become unrepairable".
 *
 * It lives inside the accent card on the landing, over the day-of-stay surface
 * the card already draws. That pairing is the argument: the numbers on the left
 * are what the bars behind them add up to, and putting the two on separate
 * screens made the reader hold one in their head while looking at the other.
 * `variant="surface"` is the styling for that context — glass on brand colour
 * rather than panels on canvas.
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

export function Dashboard({
  payload,
  variant = 'panel',
}: {
  payload: Payload
  variant?: 'panel' | 'surface'
}) {
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

  // Findings per day of stay, straight off the surface the card is drawing.
  // Same cells, two encodings: the bars behind are per episode, this is their
  // sum. Nothing is recomputed that the pipeline did not already produce.
  const perDay: number[] = []
  for (const c of payload.surface.cells) {
    perDay[c.d] = (perDay[c.d] ?? 0) + c.flags
  }
  const trend = Array.from({ length: perDay.length }, (_, d) => ({
    x: d,
    y: perDay[d] ?? 0,
  }))

  const remedyBars = (['QUERY', 'OBTAIN', 'RECODE'] as Remedy[]).map((r) => ({
    key: r,
    label: REMEDY[r].label,
    value: byRemedy(r),
    color: `var(--${REMEDY[r].css})`,
    note: REMEDY[r].who,
  }))

  const verdictSlices = [
    {
      key: 'flagged',
      label: 'Perlu perbaikan',
      value: flagged.length,
      color: 'var(--query)',
    },
    {
      key: 'clean',
      label: 'Tidak ada temuan',
      value: eps.length - flagged.length - abstain.length,
      color: 'var(--recode)',
    },
    {
      key: 'abstain',
      label: 'Perlu penilaian koder',
      value: abstain.length,
      color: 'var(--obtain)',
    },
  ]

  return (
    <section className={'view dash' + (variant === 'surface' ? ' on-surface' : '')}>
      {variant === 'panel' && <h1>Ringkasan unit</h1>}

      {payload.generated.advisory && (
        <p className="dash-warn">
          Berjalan tanpa lapisan model. Angka di bawah adalah batas bawah.
        </p>
      )}

      {/* The one number the screen leads with, and the only prose left on it.
          It is the figure that decays overnight; everything else keeps. */}
      <div className={'lead' + (onWardQueries ? ' urgent' : '')}>
        <b>{onWardQueries}</b>
        <div>
          <strong>perlu dokter selagi pasien masih di ruangan</strong>
          <span>
            {onWardQueries
              ? `${admitted.length} pasien masih dirawat. Jendela ini tertutup saat mereka pulang.`
              : admitted.length
                ? `${admitted.length} pasien masih dirawat, tidak ada yang perlu dokter.`
                : 'Tidak ada pasien yang masih dirawat pada kohort ini.'}
          </span>
        </div>
      </div>

      <div className="panels">
        <figure className="cpanel">
          <figcaption>
            Siapa yang harus bertindak
            <span>{flags.length} temuan</span>
          </figcaption>
          <BarRows data={remedyBars} />
        </figure>

        <figure className="cpanel">
          <figcaption>
            Status {eps.length} klaim
            <span>{ungroupable.length} tanpa kelompok tarif</span>
          </figcaption>
          <StackedBar data={verdictSlices} />
          <Stat
            label="Dapat dipulihkan"
            value={jt(recoverable)}
            sub="selisih tarif, dari grouper"
          />
        </figure>

        <figure className="cpanel wide">
          <figcaption>
            Temuan menurut hari rawat
            <span>
              {m
                ? `${Math.round(m.detection_rate * 100)}% terdeteksi sebelum pulang`
                : 'belum diukur'}
            </span>
          </figcaption>
          <AreaTrend
            points={trend}
            color="var(--query)"
            markX={m?.lead_time_median_days ?? null}
          />
          <TrendTicks
            maxDay={Math.max(0, trend.length - 1)}
            markLabel={
              m?.lead_time_median_days != null
                ? `median ${m.lead_time_median_days} hari lebih awal`
                : undefined
            }
          />
        </figure>
      </div>

      {/* The table is not the screen, but it is never gated: colour and hover
          both have a text fallback one click away. */}
      <details className="dash-table">
        <summary>Lihat angkanya</summary>
        <table className="dash-tbl">
          <tbody>
            {remedyBars.map((b) => (
              <tr key={b.key}>
                <td>{b.note}</td>
                <td className="num">{b.value}</td>
              </tr>
            ))}
            {verdictSlices.map((v) => (
              <tr key={v.key}>
                <td>{v.label}</td>
                <td className="num">{v.value}</td>
              </tr>
            ))}
            {m && (
              <tr>
                <td>Jendela perbaikan ≥ 2 hari</td>
                <td className="num">
                  {m.lead_time_share_ge_2_days !== null
                    ? `${Math.round(m.lead_time_share_ge_2_days * 100)}%`
                    : '—'}
                </td>
              </tr>
            )}
            <tr>
              <td>Panggilan model bahasa</td>
              <td className="num">{llmCalls}</td>
            </tr>
          </tbody>
        </table>
      </details>

      <p className="dash-foot">
        {llmCalls === 0 ? 'Tanpa' : llmCalls} panggilan model bahasa
        {llmCalls === 0 ? '' : ` (${Math.round((zeroLlm / Math.max(1, eps.length)) * 100)}% episode nihil)`}
        . Deteksi dikerjakan aturan dan{' '}
        <Term k="cross-encoder">cross-encoder</Term> di rumah sakit. Tidak ada
        angka per koder di layar ini, dan tidak akan pernah ada.
      </p>
    </section>
  )
}
