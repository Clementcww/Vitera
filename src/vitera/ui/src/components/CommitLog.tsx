import type { CommitEntry } from '../commits'
import { commitBundle, downloadJSON } from '../commits'

/* The other end of the commit button.
 *
 * A commit that leaves no visible trace is a toast message with extra steps, so
 * the record is on the screen, in the same pane as the queue, and it survives a
 * reload. It also has to be removable: this is a demo cohort, and a log that
 * cannot be reset makes the next run start dirty.
 *
 * The status word is `DRAF` everywhere and is not a style choice. Anyone who
 * opens the exported file later never saw the tray, so the disclaimer travels
 * inside the file too -- see `commitBundle`.
 */

const when = (iso: string) => {
  const d = new Date(iso)
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
}

export function CommitLog({
  entries,
  onReset,
}: {
  entries: CommitEntry[]
  onReset: () => void
}) {
  if (!entries.length) return null

  const total = entries.reduce((n, e) => n + e.items.length, 0)

  return (
    <details className="help commitlog">
      <summary>
        Riwayat commit ({entries.length})
        <span className="hint">
          {total} perbaikan disetujui koder, tersimpan di peramban ini
        </span>
      </summary>
      <div className="detail">
        <ul className="commitlist">
          {entries.map((e) => (
            <li key={e.id}>
              <div className="chead">
                <b>{e.by}</b>
                <span className="mono">{when(e.at)}</span>
                <span className="cdraf">DRAF</span>
              </div>
              <span className="cbody">
                {e.items.length} perbaikan · kohort seed{' '}
                <span className="mono">{e.seed}</span> ·{' '}
                {[...new Set(e.items.map((i) => i.episode_id))].join(', ')}
              </span>
            </li>
          ))}
        </ul>
        <p className="cnote">
          Belum ditulis ke sistem klaim rumah sakit dan tidak dikirim ke BPJS.
          Unduh berkasnya untuk dilampirkan ke berkas klaim lewat sistem rumah
          sakit.
        </p>
        <div className="tright">
          <button className="act" onClick={onReset}>
            Hapus riwayat
          </button>
          <button
            className="act primary"
            onClick={() =>
              downloadJSON(
                `vitera-draf-perbaikan-${new Date().toISOString().slice(0, 10)}.json`,
                commitBundle(entries),
              )
            }
          >
            Unduh berkas perbaikan
          </button>
        </div>
      </div>
    </details>
  )
}
