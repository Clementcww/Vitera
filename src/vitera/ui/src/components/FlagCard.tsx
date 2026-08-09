import { useState } from 'react'
import type { Flag } from '../types'
import { explain, keyStore } from '../llm'
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
  /* The provider layer, when a judge has supplied a key. It is additive: the
     deterministic rationale stays on screen and the generated sentence appears
     beneath it, labelled. Architectural rule 2 is easier to believe when you
     can see which layer wrote which line. */
  const [prose, setProse] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const hasKey = Boolean(keyStore.get())

  const ask = async () => {
    setBusy(true)
    setErr(null)
    try {
      setProse(
        await explain(
          {
            defect: flag.defect_label,
            rationale: flag.rationale,
            quote: flag.span.text,
          },
          { key: keyStore.get(), model: keyStore.model() },
        ),
      )
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
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

          {prose && (
            <p className="whyai prose">
              <span className="ailabel">ditulis model</span>
              {prose}
            </p>
          )}
          {err && <p className="whyerr">{err}</p>}

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
            {hasKey && !prose && (
              <button
                className="act"
                onClick={(e) => {
                  e.stopPropagation()
                  void ask()
                }}
                disabled={busy}
              >
                {busy ? 'Menulis…' : 'Jelaskan'}
              </button>
            )}
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
