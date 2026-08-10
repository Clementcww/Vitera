import { useState } from 'react'

/* Architectural rule 1, made visible.
 *
 * The agent drafts, stages and prepares. A human commits. Everything the koder
 * clicks lands here first; nothing is applied to the claim of record, nothing
 * is submitted to BPJS, and nothing is sent to a DPJP. A drafted query is
 * printed and handed over in person.
 *
 * The commit button used to be a dead end, on the reasoning that a button
 * which looks like it committed something is worse than one that says it did
 * not. That reasoning stands; what was missing was the thing it named as the
 * precondition: "the staging and the commit both have to be logged before
 * either is real". `commits.ts` is that log, so the button now does exactly
 * what it can honestly do -- record a named human's acceptance, durably, and
 * hand back a file -- and says plainly what it still does not do.
 *
 * The name field is not ceremony. An audit record that cannot say WHO accepted
 * a correction is not an audit record.
 */

export function StagingTray({
  items,
  onClear,
  onCommit,
}: {
  items: string[]
  onClear: () => void
  onCommit: (by: string) => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [by, setBy] = useState('')

  if (!items.length) return null

  const commit = () => {
    const name = by.trim()
    if (!name) return
    onCommit(name)
    setBy('')
    setConfirming(false)
  }

  return (
    <div className="tray">
      <div className="tleft">
        <b>{items.length}</b> perbaikan disiapkan
        <span className="tnote">
          Baru disiapkan, belum masuk berkas klaim. Yang memutuskan tetap
          manusia.
        </span>
      </div>

      {confirming ? (
        /* The confirm step exists to carry the disclaimer at the moment of
           the decision, not in a footnote read earlier or never. */
        <div className="tconfirm">
          <label>
            Nama koder yang menyetujui
            <input
              autoFocus
              value={by}
              onChange={(e) => setBy(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && commit()}
              placeholder="mis. Sri Wahyuni"
            />
          </label>
          <span className="tnote">
            Tercatat sebagai draf perbaikan dan bisa diunduh. <b>Tidak</b>
            ditulis ke sistem klaim rumah sakit dan <b>tidak</b> dikirim ke
            BPJS; penerapannya tetap lewat sistem rumah sakit.
          </span>
          <div className="tright">
            <button className="act" onClick={() => setConfirming(false)}>
              Batal
            </button>
            <button className="act primary" onClick={commit} disabled={!by.trim()}>
              Catat commit
            </button>
          </div>
        </div>
      ) : (
        <div className="tright">
          <button className="act" onClick={onClear}>
            Kosongkan
          </button>
          <button className="act primary" onClick={() => setConfirming(true)}>
            Commit ke berkas klaim
          </button>
        </div>
      )}
    </div>
  )
}
