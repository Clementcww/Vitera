import type {
  EpisodeView,
  Flag,
  Loaded,
  Payload,
  SeedManifest,
  SweepPayload,
} from './types'

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
 * counted, never rendered with a softened citation, never rendered without
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
 * than cosmetic: a Query needs the DPJP while the patient is still on the
 * ward, so it decays fastest and must surface first however small its rupiah
 * figure. Sorting by value alone would bury the only findings that expire.
 *
 * Applied by the QUEUE, not here, and only once the sweep has staged one.
 * Ordering is the sweep's job (`sweep/queue.py`, and CLAUDE.md's build order
 * lists it there), so a screen that has not been swept must not already be in
 * queue order or the sweep appears to do nothing. */
export function queueOrder(a: EpisodeView, b: EpisodeView): number {
  const rank = (e: EpisodeView) =>
    e.flags.length ? Math.min(...e.flags.map((f) => f.decay_rank)) : 99
  const value = (e: EpisodeView) => e.money.delta_idr ?? 0
  return rank(a) - rank(b) || value(b) - value(a) || a.los_so_far - b.los_so_far
}

export async function load(url = './data/demo.json'): Promise<Loaded> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}. Run \`make ui-data\``)
  const payload: Payload = await res.json()

  let droppedFlags = 0
  for (const ep of payload.episodes) {
    const { flags, dropped } = verifySpans(ep)
    ep.flags = flags
    droppedFlags += dropped
  }
  /* Registry order, which is what an unswept work list actually looks like:
     the episodes in episode-number order, the same order `sweep/runner.py`
     reads its cohort in.
     Deliberately NOT shuffled. Scrambling the rows would make the un-swept
     screen worse than reality in order to flatter the swept one, which is the
     strawman-baseline problem CLAUDE.md rules out for the arms; a demo is not
     exempt from it just because no number is printed underneath. */
  payload.episodes.sort((a, b) => a.episode_id.localeCompare(b.episode_id))
  return { payload, droppedFlags }
}

/** The sweep's output, written by `make sweep-demo`.
 *
 * Optional on purpose and deliberately not awaited with the main payload: the
 * workbench must still open when no sweep has run. What it must NOT do is
 * invent a timestamp. A missing file means the header says the queue has no
 * sweep behind it, which is honest, rather than rendering as fresh. */
export async function loadSweep(
  url = './data/sweep.json',
): Promise<SweepPayload | null> {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    return (await res.json()) as SweepPayload
  } catch {
    return null
  }
}

/** The cohorts the seed control may switch between, or null.
 *
 * Optional, like the sweep: a workbench where `make ui-seeds` has never run
 * still opens, on the canonical cohort, with no seed control offered. Absent
 * is rendered as absent rather than as a list of one, because a control with a
 * single option invites the reader to look for the others. */
export async function loadSeeds(
  url = './data/seeds.json',
): Promise<SeedManifest | null> {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    const m = (await res.json()) as SeedManifest
    return m?.seeds?.length ? m : null
  } catch {
    return null
  }
}

/** Hours since the last SUCCESSFUL sweep. Sweep rule 5's `queue_staleness`.
 *
 * Measured against `last_successful_sweep`, never `last_attempted_sweep`. A
 * night that ran and failed leaves the queue exactly as stale as a night that
 * never ran, and the screen has to say the same thing about both.
 *
 * In replay mode the dates are synthetic (derived from the corpus, not from a
 * clock), so staleness is not meaningful and returns null rather than a large
 * scary number the demo would have to explain away. */
export function staleHours(s: SweepPayload | null): number | null {
  if (!s || !s.last_successful_sweep || s.generated.mode === 'replay') return null
  const then = Date.parse(s.last_successful_sweep + 'T02:00:00Z')
  if (Number.isNaN(then)) return null
  return Math.max(0, (Date.now() - then) / 3_600_000)
}
