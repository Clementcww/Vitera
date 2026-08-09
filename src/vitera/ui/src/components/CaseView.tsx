import { useState } from 'react'
import type { EpisodeView, Remedy } from '../types'
import { REMEDY, VERDICT, rp, tariff } from '../format'
import { FlagCard } from './FlagCard'
import { DocPane } from './DocPane'

/* The workbench. Verdict above the fold, findings grouped by who acts,
 * documents beside them with the cited span highlighted in place.
 *
 * The money strip is two grouper calls and a subtraction the exporter did:
 * what the claim groups to with the unsupported codes removed, and what it
 * would group to if the DPJP confirms what the record already suggests. Both
 * are badged `grouper`. An ungroupable episode shows a dash and the reason —
 * estimating a tariff there is explicitly forbidden. */

const ORDER: Remedy[] = ['QUERY', 'OBTAIN', 'RECODE']

const byRemedy = (ep: EpisodeView, k: Remedy) =>
  ep.flags.filter((f) => f.remedy === k)

export function CaseView({
  ep,
  staged,
  onStage,
  onDismiss,
  onBack,
}: {
  ep: EpisodeView
  staged: Set<string>
  onStage: (key: string) => void
  onDismiss: (key: string) => void
  onBack: () => void
}) {
  const [openFlag, setOpenFlag] = useState<string | null>(null)
  const active = ep.flags.find(
    (f) => openFlag?.includes(f.span.evidence_hash) ?? false,
  )

  return (
    <section className="view">
      <div className="crumb">
        <button onClick={onBack}>← Queue</button>
        <span>/</span>
        <span className="mono">{ep.episode_id}</span>
      </div>

      <div className="verdict">
        <div className="vtop">
          <span className={'vword v-' + ep.verdict}>
            <span className="d" />
            {VERDICT[ep.verdict]}
          </span>
          <h2 className="mono">{ep.episode_id}</h2>
          <span className="who">
            {ep.site_id} · day {ep.day} of stay ·{' '}
            {ep.still_admitted ? 'still admitted' : 'discharged'}
          </span>
          {!ep.still_admitted && byRemedy(ep, 'QUERY').length > 0 && (
            <span className="windowshut">
              the window has shut; the doctor would be reconstructing from memory
            </span>
          )}
        </div>

        <div className="strip">
          <div className="kv">
            <div className="k">Tarif saat ini</div>
            <div className="v mono">
              {tariff(ep.money.now)}
              <span className="src">grouper</span>
            </div>
          </div>
          <div className="kv">
            <div className="k">If confirmed</div>
            <div className="v mono">
              {tariff(ep.money.if_confirmed)}
              {ep.money.delta_idr ? (
                <small>+{rp(ep.money.delta_idr)}</small>
              ) : null}
            </div>
          </div>
          <div className="kv">
            <div className="k">Grup</div>
            <div className="v mono">
              {ep.money.now.cbg_code ?? '—'}
              {ep.money.now.ungroupable_reason && (
                <small className="warn">{ep.money.now.ungroupable_reason}</small>
              )}
            </div>
          </div>
          <div className="kv">
            <div className="k">Findings</div>
            <div className="v mono">
              {ep.flags.length}
              {/* NOT `verdict_reason` — that string names the raw router
                  threshold, which is an internal number and reads as noise to
                  a koder. It stays, verbatim, in the audit trace below. */}
              <small>
                {ORDER.filter((k) => byRemedy(ep, k).length)
                  .map((k) => `${byRemedy(ep, k).length} ${REMEDY[k].label}`)
                  .join(' · ') || 'nothing found'}
              </small>
            </div>
          </div>
        </div>
      </div>

      <div className="split">
        <div className="panel">
          <div className="phd">
            <h3>What to fix</h3>
            <span className="c">grouped by who acts</span>
          </div>
          {ep.flags.length === 0 && (
            <p className="empty prose">{ep.verdict_reason}</p>
          )}
          {ORDER.map((k) => {
            const rows = byRemedy(ep, k)
            if (!rows.length) return null
            return (
              <div className="grp" key={k}>
                <div className="ghd">
                  <span
                    className="sw"
                    style={{ background: `var(--${REMEDY[k].css})` }}
                  />
                  <span className="nm">{REMEDY[k].label}</span>
                  <span className="wd">{REMEDY[k].who}</span>
                </div>
                {rows.map((f, i) => {
                  /* The index is load-bearing, not React ceremony.
                     `Flag.suppression_key` is defect_class + evidence_hash, and
                     two findings about DIFFERENT codes collide on it whenever
                     they cite the same anchor line — which D5 and D7 do all the
                     time, because an absence-based finding cites the berkas
                     cover sheet. Without the index, staging or dismissing one
                     silently applies to the other. See the note in
                     docs/ARCHITECTURE.md; the real fix is a subject field on
                     Flag, which is a contract change and belongs to bucket 13. */
                  const key = `${ep.episode_id}:${f.defect_class}:${f.span.evidence_hash}:${i}`
                  return (
                    <FlagCard
                      key={key}
                      flag={f}
                      open={openFlag === key}
                      staged={staged.has(key)}
                      onToggle={() => setOpenFlag(openFlag === key ? null : key)}
                      onStage={() => onStage(key)}
                      onDismiss={() => onDismiss(key)}
                    />
                  )
                })}
              </div>
            )
          })}
        </div>

        <DocPane
          documents={ep.documents}
          flags={ep.flags}
          activeDoc={active?.span.doc_id ?? null}
        />
      </div>

      <details className="help">
        <summary>Run trace</summary>
        <div className="detail">
          <div className="tracegrid mono">
            <span>panggilan LLM</span>
            <b>{ep.trace.llm_calls}</b>
            <span>budget exceeded</span>
            <b>{ep.trace.budget_breach ?? 'none'}</b>
            <span>durasi</span>
            <b>{ep.trace.elapsed_seconds.toFixed(4)} s</b>
            <span>tools run</span>
            <b>
              {ep.trace.tool_calls.map((t) => `${t.tool} (${t.result_digest})`).join(', ') ||
                '—'}
            </b>
            <span>classes checked</span>
            <b>{ep.classes_checked.join(', ')}</b>
            <span>router decision</span>
            <b>{ep.verdict_reason}</b>
          </div>
        </div>
      </details>
    </section>
  )
}
