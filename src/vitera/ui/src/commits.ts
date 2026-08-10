/* The commit record. Architectural rule 1's other half.
 *
 * The tray always said "a human commits" and then offered a dead button, which
 * demonstrated the rule by failing to implement it. The blocker named in
 * StagingTray.tsx was never the write itself: it was that "the staging and the
 * commit both have to be logged before either is real". So this is the log.
 *
 * What a commit here IS: a durable, timestamped record that a named human
 * accepted a set of drafted corrections, exportable as a file that can be
 * attached to the claim bundle.
 *
 * What it is NOT, and must never render as: a write to the hospital's claim of
 * record, or anything sent to BPJS. That integration does not exist, and a
 * button that appears to have submitted a claim is the one failure this whole
 * screen is built to avoid. Every surface that shows a commit says so.
 */

export type CommitItem = {
  key: string
  episode_id: string
  defect_class: string
  evidence_hash: string
}

export type CommitEntry = {
  id: string
  at: string
  seed: number
  by: string
  items: CommitItem[]
}

const KEY = 'vitera.commits.v1'

/** Staged keys are `episode:defect_class:evidence_hash:index` (see CaseView). */
export function parseKey(key: string): CommitItem {
  const [episode_id = key, defect_class = '', evidence_hash = ''] = key.split(':')
  return { key, episode_id, defect_class, evidence_hash }
}

/* localStorage throws in private mode and when the origin is opaque, and the
   demo runs from a file server on a borrowed laptop. A commit log that takes
   the app down is worse than one that does not persist, so every access is
   fenced and failure degrades to in-memory only. */
export function readCommits(): CommitEntry[] {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as CommitEntry[]) : []
  } catch {
    return []
  }
}

export function writeCommits(entries: CommitEntry[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries))
  } catch {
    /* in-memory only for this session; the caller still has the entries */
  }
}

export function newCommit(
  keys: string[],
  seed: number,
  by: string,
): CommitEntry {
  return {
    // Date.now plus a short random tail: two commits in the same millisecond
    // would otherwise share a React key and an audit id.
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    at: new Date().toISOString(),
    seed,
    by,
    items: keys.map(parseKey),
  }
}

/** The exported bundle. Carries its own disclaimer, because a file outlives
 *  the screen that produced it and will be opened by someone who never saw
 *  the tray. */
export function commitBundle(entries: CommitEntry[]) {
  return {
    generated_by: 'Vitera workbench',
    generated_at: new Date().toISOString(),
    status: 'DRAF',
    disclaimer:
      'Catatan perbaikan yang disetujui koder. Ini DRAF: belum ditulis ke ' +
      'sistem klaim rumah sakit dan tidak dikirim ke BPJS. Penerapan ke ' +
      'berkas klaim resmi dilakukan manusia melalui sistem rumah sakit.',
    commits: entries,
  }
}

export function downloadJSON(name: string, data: unknown): void {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
  )
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}
