import type { Doc, Flag } from '../types'

/* L3 — the cited span highlighted in place, inside the document it came from.
 *
 * A detached citation list does not survive scrutiny: a koder cannot tell
 * whether a quote was lifted out of context without seeing the context. So the
 * highlight is applied to the real document text, by offset, never by string
 * search. Searching would silently highlight the wrong occurrence when a
 * phrase repeats — and CPPT text repeats constantly.
 *
 * A document dropped from the claim file by D1/D5 renders as absent with no
 * body. That absence is itself a finding elsewhere in the queue; hiding the
 * row would hide it. */

function Highlighted({ text, spans }: { text: string; spans: Flag[] }) {
  if (!spans.length) return <>{text}</>

  const marks = [...spans].sort((a, b) => a.span.start - b.span.start)
  const out: React.ReactNode[] = []
  let cursor = 0

  marks.forEach((f, i) => {
    const { start, end } = f.span
    if (start < cursor) return // overlapping citation; first one wins
    out.push(text.slice(cursor, start))
    out.push(
      <mark key={i} className={'m-' + f.remedy.toLowerCase()}>
        {text.slice(start, end)}
      </mark>,
    )
    cursor = end
  })
  out.push(text.slice(cursor))
  return <>{out}</>
}

export function DocPane({
  documents,
  flags,
  activeDoc,
}: {
  documents: Doc[]
  flags: Flag[]
  activeDoc: string | null
}) {
  return (
    <div className="panel">
      <div className="phd">
        <h3>Rekam medis</h3>
        <span className="c">sebatas hari yang diperiksa</span>
      </div>
      {documents.map((d) => {
        const cited = flags.filter((f) => f.span.doc_id === d.doc_id)
        return (
          <details
            key={d.doc_id}
            className={'doc' + (d.absent ? ' absent' : '')}
            open={activeDoc === d.doc_id || undefined}
          >
            <summary>
              <span className="nm mono">{d.doc_id}</span>
              <span className="mt">
                {cited.length > 0 && <span className="cited" />}
                {d.absent ? 'tidak dilampirkan' : `hari ${d.day}`}
              </span>
            </summary>
            <div className="body prose">
              {d.absent ? (
                <span className="muted">
                  Dokumen ini tidak ada pada berkas klaim, jadi tidak ada temuan
                  yang boleh mengutipnya.
                </span>
              ) : (
                <Highlighted text={d.text} spans={cited} />
              )}
            </div>
          </details>
        )
      })}
    </div>
  )
}
