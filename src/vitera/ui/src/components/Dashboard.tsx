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
      <h1>Unit summary</h1>
      <p className="lede">
        {payload.generated.cohort} inpatient episodes, {admitted.length} of them
        still on the ward this morning. Every rupiah figure is the
        grouper&rsquo;s; episodes it could not group are counted here but left
        out of the money.
      </p>

      {payload.generated.advisory && (
        <p className="dash-warn">
          The last run had no model layer. Some defect classes went
          unchecked, so everything below is a floor, not a total.
        </p>
      )}

      <div className={'lead' + (onWardQueries ? ' urgent' : '')}>
        <b>{onWardQueries}</b>
        <div>
          <strong>need the doctor while the patient is still on the ward</strong>
          <span>
            {onWardQueries
              ? 'These shut at discharge. Everything else can wait a day.'
              : admitted.length
                ? 'Nothing on the ward needs the doctor this morning.'
                : 'No episode in this cohort is still admitted, so no repair window is open.'}
          </span>
        </div>
      </div>

      <div className="stats">
        <Stat
          label="Claims with findings"
          value={`${flagged.length} / ${eps.length}`}
          sub={abstain.length ? `${abstain.length} need a coder to judge` : undefined}
        />
        <Stat
          label="Recoverable"
          value={jt(recoverable)}
          sub="tariff difference, from the grouper"
        />
        <Stat
          label="Could not be grouped"
          value={String(ungroupable.length)}
          sub={ungroupable.length ? 'no tariff estimated' : 'none'}
        />
      </div>

      <h2 className="dash-h">Who has to act</h2>
      <table className="dash-tbl">
        <thead>
          <tr>
            <th>Who</th>
            <th>Findings</th>
            <th>Time left</th>
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
                  ? 'until the patient goes home'
                  : r === 'OBTAIN'
                    ? 'until the file is sent'
                    : 'until the claim is submitted'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 className="dash-h">Detection</h2>
      {m ? (
        <div className="stats">
          <Stat
            label="Found before discharge"
            value={`${Math.round(m.detection_rate * 100)}%`}
            sub={`n = ${m.n_episodes}`}
          />
          <Stat
            label="Found this early"
            value={m.lead_time_median_days !== null ? `${m.lead_time_median_days} days` : '—'}
            sub="median, before discharge"
          />
          <Stat
            label="Two days or more to act"
            value={
              m.lead_time_share_ge_2_days !== null
                ? `${Math.round(m.lead_time_share_ge_2_days * 100)}%`
                : '—'
            }
            sub="still repairable"
          />
        </div>
      ) : (
        <p className="dash-empty">Not yet measured on the held-out split.</p>
      )}

      {/* Precision matters here: `llm_calls` counts calls to the language
          model, which writes prose and decides nothing. Every episode was
          still scored by the cross-encoder, which is a model — so "no LLM
          call" is true and "deterministic rules alone" would not be. */}
      <p className="dash-cost">
        <span>{llmCalls}</span> language-model calls across the cohort ·{' '}
        <span>{Math.round((zeroLlm / Math.max(1, eps.length)) * 100)}%</span> of
        episodes settled with no language-model call at all. Detection is rules
        plus the in-hospital <Term k="cross-encoder">cross-encoder</Term>; the
        language model only writes the explanations.
      </p>

      <p className="dash-foot">
        There are no per-coder figures on this screen and there will not be.
        A queue that doubles as a performance review is a queue that gets
        closed rather than worked.
      </p>
    </section>
  )
}
