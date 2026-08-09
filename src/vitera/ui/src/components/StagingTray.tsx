/* Architectural rule 1, made visible.
 *
 * The agent drafts, stages and prepares. A human commits. Everything the koder
 * clicks lands here first; nothing is applied to the claim of record, nothing
 * is submitted to BPJS, and nothing is sent to a DPJP — a drafted query is
 * printed and handed over in person.
 *
 * The commit button is deliberately a dead end in this build. Wiring it to a
 * write would need the claim-of-record integration that does not exist and,
 * more to the point, the staging and the commit both have to be logged before
 * either is real. A button that looks like it committed something is worse
 * than one that says it did not. */

export function StagingTray({
  items,
  onClear,
}: {
  items: string[]
  onClear: () => void
}) {
  if (!items.length) return null

  return (
    <div className="tray">
      <div className="tleft">
        <b>{items.length}</b> perbaikan disiapkan
        <span className="tnote">
          not applied yet, needs a human to commit
        </span>
      </div>
      <div className="tright">
        <button className="act" onClick={onClear}>
          Kosongkan
        </button>
        <button
          className="act primary"
          title="Not active in this build: writing to the claim of record, and the commit log that would accompany it."
          disabled
        >
          Commit to the claim file
        </button>
      </div>
    </div>
  )
}
