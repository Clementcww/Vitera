import type { Flag } from '../types'
import { DEFECT_ID, REMEDY, SOURCE } from '../format'

/* L2 — rationale, the verbatim quote, and the two actions.
 *
 * Rule 1 is the whole design of this card: the agent drafts and stages, a
 * human commits. "Siapkan" puts a draft in the tray. Nothing is applied, and
 * nothing is sent — a drafted DPJP query is printed and handed over, because
 * the sweep may never message outward, however useful that would be.
 *
 * Rule 10 gives abstain its own treatment rather than an empty state. Saying
 * "I cannot determine this" and showing the evidence gathered is a first-class
 * output; hiding it behind a blank panel would make abstention look like a
 * failure to produce a finding. */

export function FlagCard({
  flag,
  open,
  staged,
  onToggle,
  onStage,
  onDismiss,
}: {
  flag: Flag
  open: boolean
  staged: boolean
  onToggle: () => void
  onStage: () => void
  onDismiss: () => void
}) {
  const abstain = flag.source === 'cross_encoder' && flag.score < 0.5
  const isQuery = flag.remedy === 'QUERY'

  return (
    <div className={'flag' + (open ? ' hot' : '') + (abstain ? ' abstain' : '')}>
      <button className="fsum" onClick={onToggle}>
        <span className="dcls mono">{flag.defect_class}</span>
        <span className="ftitle">
          {DEFECT_ID[flag.defect_class] ?? flag.defect_label}
        </span>
        <span className="fright">
          {staged && <span className="stagedpip">tersimpan</span>}
          {abstain && <span className="abst">abstain</span>}
          <span className="conf mono">{flag.score.toFixed(3)}</span>
        </span>
      </button>

      {open && (
        <div className="fbody">
          <p className="why">{flag.rationale}</p>

          <blockquote>
            “{flag.span.text}”
            <cite className="mono">
              {flag.span.doc_id} · {flag.span.start}–{flag.span.end}
            </cite>
          </blockquote>

          {isQuery && (
            <div className="draft">
              <b>Draf pertanyaan untuk DPJP</b>
              <span className="prose">
                “Mohon konfirmasi apakah kondisi ini ditegakkan dan dikelola pada
                perawatan ini. Bukti pada catatan: {flag.span.text}”
              </span>
              <span className="no">
                Dicetak dan diserahkan. Sistem tidak pernah mengirim apa pun
                keluar.
              </span>
            </div>
          )}

          <div className="acts">
            <button className="act primary" onClick={onStage} disabled={staged}>
              {staged
                ? 'Sudah di baki'
                : isQuery
                  ? 'Siapkan pertanyaan'
                  : 'Siapkan perbaikan'}
            </button>
            <button className="act" onClick={onDismiss}>
              Tolak
            </button>
            <span className="meta">
              {SOURCE[flag.source]} · {REMEDY[flag.remedy].label} ·{' '}
              {flag.actor}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
