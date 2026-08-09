import { useState } from 'react'
import type { EpisodeView, Remedy } from '../types'
import { DEFECT_ID, REMEDY, jt } from '../format'
import { Term } from './Term'

/* L0 and L1.
 *
 * The koder does 30–50 claims a day. The screen's job is to let them skip
 * fast, so a row is one line until asked: who acts, how much window is left,
 * how much is recoverable. Findings appear on expand; the workbench is a
 * second click.
 *
 * Rupiah come from the grouper and are badged as such. An episode the grouper
 * could not group shows a dash — never an estimate (rule 7). */

type Filter = 'ALL' | Remedy

function topRemedy(e: EpisodeView): Remedy | null {
  if (!e.flags.length) return null
  return e.flags.reduce((a, b) => (a.decay_rank <= b.decay_rank ? a : b)).remedy
}

export function QueueView({
  episodes,
  onOpen,
}: {
  episodes: EpisodeView[]
  onOpen: (id: string) => void
}) {
  const [filter, setFilter] = useState<Filter>('ALL')
  const [open, setOpen] = useState<string | null>(null)

  const counts: Record<string, number> = { ALL: episodes.length }
  for (const r of ['QUERY', 'OBTAIN', 'RECODE'] as Remedy[]) {
    counts[r] = episodes.filter((e) => topRemedy(e) === r).length
  }

  const shown = episodes.filter((e) => filter === 'ALL' || topRemedy(e) === filter)

  return (
    <section className="view">
      <h1>Antrean pagi</h1>
      <p className="lede">
        Daftar <Term k="klaim">klaim</Term> yang perlu ditindaklanjuti pagi
        ini, terurut menurut jendela perbaikan. Yang butuh dokter selagi
        pasien masih dirawat naik paling atas.
      </p>

      <details className="help" style={{ margin: '0 0 16px' }}>
        <summary>Baru pertama kali melihat layar ini?</summary>
        <div className="detail">
          Setiap baris adalah tagihan satu pasien ke{' '}
          <Term k="bpjs">BPJS</Term>. Warna menunjukkan siapa yang harus
          bertindak: <b style={{ color: 'var(--query)' }}>oranye</b> untuk dokter (
          <Term k="dpjp">DPJP</Term>), selagi pasien masih di ruangan;{' '}
          <b style={{ color: 'var(--obtain)' }}>biru</b> untuk petugas berkas,
          melengkapi dokumen; <b style={{ color: 'var(--recode)' }}>hijau</b> untuk{' '}
          <Term k="koder">koder</Term>, memperbaiki kode. Kolom rupiah adalah
          selisih tarif yang bisa diselamatkan bila catatan dilengkapi,
          dihitung <Term k="grouper">grouper</Term>, bukan model AI. Klik baris
          untuk melihat temuannya; setiap temuan mengutip dokumen aslinya{' '}
          <Term k="verbatim">kata demi kata</Term>.
        </div>
      </details>

      <div className="filters">
        {(['ALL', 'QUERY', 'OBTAIN', 'RECODE'] as Filter[]).map((f) => (
          <button
            key={f}
            className={'f' + (filter === f ? ' on' : '')}
            onClick={() => setFilter(f)}
          >
            {f !== 'ALL' && (
              <span
                className="sw"
                style={{ background: `var(--${REMEDY[f].css})` }}
              />
            )}
            {f === 'ALL' ? 'Semua' : REMEDY[f].label}
            <span className="n">{counts[f]}</span>
          </button>
        ))}
      </div>

      <div className="list">
        {shown.map((e) => {
          const rm = topRemedy(e)
          const expanded = open === e.episode_id
          const delta = e.money.delta_idr
          return (
            <div className={'row' + (expanded ? ' open' : '')} key={e.episode_id}>
              <button
                className="rsum"
                onClick={() => setOpen(expanded ? null : e.episode_id)}
              >
                <span
                  className="rdot"
                  style={{ background: rm ? `var(--${REMEDY[rm].css})` : 'var(--mid)' }}
                  title={rm ? REMEDY[rm].label : 'tidak ada temuan'}
                />
                <span className="rid mono">{e.episode_id}</span>
                {/* The class label is the same words on eleven consecutive
                    rows, which is unskimmable. The rationale names the actual
                    code, so it is what the koder reads; the class stays as a
                    chip for anyone scanning by defect type. */}
                <span className="rtitle">
                  {e.flags.length ? (
                    <>
                      <span
                        className="chip mono"
                        title={
                          DEFECT_ID[e.flags[0]!.defect_class] ??
                          e.flags[0]!.defect_label
                        }
                      >
                        {e.flags[0]!.defect_class}
                      </span>
                      {e.flags[0]!.rationale}
                    </>
                  ) : (
                    <span className="muted">
                      Tidak ada temuan pada pemeriksaan ini
                    </span>
                  )}
                </span>
                <span className="rmeta">
                  {e.site_id} · h{e.day}
                  {e.still_admitted ? ' · dirawat' : ''}
                </span>
                <span className="rmoney">
                  {e.money.now.ungroupable_reason ? (
                    <span className="none" title={e.money.now.ungroupable_reason}>
                      —
                    </span>
                  ) : delta ? (
                    jt(delta)
                  ) : (
                    <span className="none">·</span>
                  )}
                </span>
                <span className="rcount">{e.flags.length || ''}</span>
              </button>

              {expanded && (
                <div className="rbody">
                  {e.flags.length ? (
                    e.flags.map((f, i) => (
                      <div className="mini" key={i}>
                        <span className="c mono">{f.defect_class}</span>
                        <span className="t">{f.rationale}</span>
                        <span className="s mono">{f.score.toFixed(3)}</span>
                      </div>
                    ))
                  ) : (
                    <div className="mini muted">{e.verdict_reason}</div>
                  )}
                  <button className="open-btn" onClick={() => onOpen(e.episode_id)}>
                    Buka workbench →
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <details className="help">
        <summary>Bagaimana antrean ini diurutkan?</summary>
        <div className="detail">
          Urutan <code>remedy_decay_rank → expected_value → day_of_stay</code>.
          Query naik lebih dulu karena jendelanya tutup saat pasien pulang;
          Obtain masih bisa dikejar setelah pulang; Recode masih bisa sampai
          berkas disubmit. Kolom rupiah seluruhnya keluaran grouper. Model
          tidak pernah menghasilkan angka uang, dan episode{' '}
          <code>UNGROUPABLE</code> ditampilkan sebagai tanda hubung.
        </div>
      </details>
    </section>
  )
}
