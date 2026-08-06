import type { EpisodeView, Flag, Loaded, Payload } from './types'

/* Loading, and the client half of architectural rule 6.
 *
 * The pipeline already ran `filter_spans` before anything was exported. This
 * runs the same check again, in the browser, against the document text the
 * screen is about to render:
 *
 *     doc.text.slice(span.start, span.end) === span.text
 *
 * Doing it twice is deliberate. The Python filter protects the pipeline; this
 * one protects the *screen*, which is the surface a poisoned note would have
 * to reach to do damage. If a span does not survive, the flag is dropped and
 * counted — never rendered with a softened citation, never rendered without
 * one. A finding that cannot point at the record is not a finding.
 *
 * `droppedFlags` is surfaced in the UI. A silent drop would make this checkbox
 * theatre rather than a control.
 */

export function verifySpans(ep: EpisodeView): { flags: Flag[]; dropped: number } {
  const byDoc = new Map(ep.documents.map((d) => [d.doc_id, d]))
  const kept: Flag[] = []
  let dropped = 0

  for (const f of ep.flags) {
    const doc = byDoc.get(f.span.doc_id)
    if (!doc || doc.absent) {
      dropped++
      continue
    }
    if (doc.text.slice(f.span.start, f.span.end) !== f.span.text) {
      dropped++
      continue
    }
    kept.push(f)
  }
  return { flags: kept, dropped }
}

/** Queue order: remedy decay first, then recoverable value, then day of stay.
 *
 * Matches `config/sweep.yaml`'s ordering, and the reason is clinical rather
 * than cosmetic — a Query needs the DPJP while the patient is still on the
 * ward, so it decays fastest and must surface first however small its rupiah
 * figure. Sorting by value alone would bury the only findings that expire. */
export function queueOrder(a: EpisodeView, b: EpisodeView): number {
  const rank = (e: EpisodeView) =>
    e.flags.length ? Math.min(...e.flags.map((f) => f.decay_rank)) : 99
  const value = (e: EpisodeView) => e.money.delta_idr ?? 0
  return rank(a) - rank(b) || value(b) - value(a) || a.los_so_far - b.los_so_far
}

export async function load(url = './data/demo.json'): Promise<Loaded> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — run \`make ui-data\``)
  const payload: Payload = await res.json()

  let droppedFlags = 0
  for (const ep of payload.episodes) {
    const { flags, dropped } = verifySpans(ep)
    ep.flags = flags
    droppedFlags += dropped
  }
  payload.episodes.sort(queueOrder)
  return { payload, droppedFlags }
}
