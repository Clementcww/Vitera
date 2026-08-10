import type { SeedManifest, SweepPayload } from '../types'

/* The two demo controls above the queue: which cohort, and run the sweep.
 *
 * ── Read this before moving either of them into the product chrome.
 *
 * CLAUDE.md locks a decision that this strip could easily be mistaken for
 * breaking: **the sweep is scheduled and unattended, and nobody presses a
 * button to make it happen.** A koder-triggered sweep is a discharge product
 * with extra steps, and saying otherwise on stage would cost us the concurrent
 * claim outright.
 *
 * So this is not a koder feature and must never read as one. It is a demo
 * control, boxed, tagged, and captioned with what actually happens in
 * production. What the button does is replay a sweep that already ran and was
 * written to `data/sweep-*.json` by `make sweep-demo`; it computes nothing,
 * exactly like every other thing this UI draws.
 *
 * The seed control is the same shape of honesty. The workbench is a static
 * bundle, so it cannot regenerate a cohort. Each option is a cohort the real
 * exporter already produced under a different seed (`make ui-seeds`), and
 * switching is a fetch. The point is to let a judge check that the demo is not
 * one flattering draw, which is a fair question to ask of a cohort we
 * deliberately stratified.
 */

export function DemoControls({
  manifest,
  seed,
  onSeed,
  swept,
  onSweep,
  sweep,
  busy,
}: {
  manifest: SeedManifest | null
  seed: number
  onSeed: (seed: number) => void
  swept: boolean
  onSweep: () => void
  sweep: SweepPayload | null
  busy: boolean
}) {
  const entries = manifest?.seeds ?? []

  return (
    <div className="democtl">
      <span className="demotag">Demo</span>

      {entries.length > 1 && (
        <div className="demorow">
          <span className="demolab">Kohort</span>
          <div className="seedpick">
            {entries.map((e) => (
              <button
                key={e.seed}
                className={'seedbtn' + (e.seed === seed ? ' on' : '')}
                disabled={busy}
                onClick={() => onSeed(e.seed)}
                title={
                  e.canonical
                    ? 'Kohort baku, sumber setiap angka yang dilaporkan'
                    : 'Kohort alternatif, diekspor pipeline yang sama'
                }
              >
                <span className="mono">{e.seed}</span>
                {e.canonical && <i aria-hidden="true">baku</i>}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="demorow">
        <span className="demolab">Sweep</span>
        {swept ? (
          <span className="sweptmark">
            <b>Sweep selesai.</b> Antrean dikelompokkan menurut siapa yang harus
            bertindak
            {sweep?.last_successful_sweep
              ? `, malam terakhir ${sweep.last_successful_sweep}`
              : ''}
            .
          </span>
        ) : (
          <button className="sweepbtn" onClick={onSweep} disabled={busy}>
            Jalankan sweep <span aria-hidden="true">→</span>
          </button>
        )}
      </div>

      {/* The sentence that keeps the locked decision intact. It stays even
          after the button is pressed, because that is when a viewer is most
          likely to conclude the sweep is something a person kicks off. */}
      <p className="demonote">
        Di produksi sweep berjalan terjadwal tiap malam tanpa dipicu siapa pun.
        Tombol ini memutar ulang sweep yang sudah dijalankan{' '}
        <code>make sweep-demo</code>, bukan menghitung ulang di peramban.
        {entries.length > 1 && (
          <>
            {' '}
            Tiap kohort adalah ekspor ulang oleh pipeline yang sama dengan seed
            berbeda. Tidak ada angka terukur yang berasal dari kohort mana pun
            di sini.
          </>
        )}
      </p>
    </div>
  )
}
