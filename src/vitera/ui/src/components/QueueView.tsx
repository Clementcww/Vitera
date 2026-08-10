import { useState } from 'react'
import type { EpisodeView, Remedy, SweepPayload } from '../types'
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
 * could not group shows a dash — never an estimate (rule 7).
 *
 * ── Two things here were fixed after watching the screen rather than reading
 * it, and both were the same mistake: a row whose distinguishing information
 * was not at its left edge.
 *
 * The row title used to open with the rationale, on the theory that naming the
 * actual code beat repeating the defect class. But the rationale is a template
 * — thirteen of forty-seven findings share one — so eleven consecutive rows
 * read "bukti klinis untuk … ada pada catatan, namun diagnosis tidak tertulis"
 * with the only varying token, the ICD code, buried mid-sentence. The subject
 * now leads and the sentence follows it.
 *
 * The `Baru`/`Naik` marks come from the sweep's diff. Without them the queue is
 * a standing list that looks identical every morning, which is precisely the
 * monitoring product that gets switched off in week two (sweep rule 3). The
 * default filter is what CHANGED since the last sweep; the standing list is one
 * click away and clearly labelled as such. */

type Filter = 'ALL' | 'DIFF' | Remedy
type DiffMark = 'new' | 'escalated' | null

function topRemedy(e: EpisodeView): Remedy | null {
  if (!e.flags.length) return null
  return e.flags.reduce((a, b) => (a.decay_rank <= b.decay_rank ? a : b)).remedy
}

/** What each episode's MOST RECENT sweep reported as new or escalated.
 *
 * Per episode, not per calendar night. The workbench shows each episode on its
 * own current day — some mid-stay, some at discharge — so "what changed" has
 * to mean *at that episode's last sweep*. Reading one shared night instead
 * marks nothing for every episode that discharged earlier in the week, and
 * marks nothing at all on a night where the whole ward happened to be quiet.
 *
 * Keyed on `suppression_key` — class, subject and evidence hash — because that
 * is exactly what the sweep wrote. Recomputing a lookalike key in the browser
 * is how a screen and a queue quietly stop agreeing. */
function diffMarks(sweep: SweepPayload | null): Map<string, DiffMark> {
  const marks = new Map<string, DiffMark>()
  if (!sweep) return marks

  const latest = new Map<string, SweepPayload['nights'][number]['queue'][number]>()
  for (const night of sweep.nights) {
    for (const item of night.queue) latest.set(item.episode_id, item)
  }
  for (const item of latest.values()) {
    for (const f of item.escalated) marks.set(f.suppression_key, 'escalated')
    for (const f of item.new) {
      if (!marks.has(f.suppression_key)) marks.set(f.suppression_key, 'new')
    }
  }
  return marks
}

export function QueueView({
  episodes,
  sweep,
  onOpen,
}: {
  episodes: EpisodeView[]
  sweep?: SweepPayload | null
  onOpen: (id: string) => void
}) {
  const marks = diffMarks(sweep ?? null)
  const changed = (e: EpisodeView) =>
    e.flags.some((f) => marks.has(f.suppression_key))

  // Default to the diff when there IS one. With no sweep output the filter is
  // not offered at all, rather than offered and silently empty.
  //
  // `chosen` starts null rather than defaulting eagerly, because the sweep
  // payload arrives one tick after the first render. Seeding `useState` with
  // the default computed on that first render freezes it at "no sweep", and
  // the queue lands on the standing list even once the diff shows up.
  const hasDiff = marks.size > 0 && episodes.some(changed)
  const [chosen, setFilter] = useState<Filter | null>(null)
  const filter: Filter = chosen ?? (hasDiff ? 'DIFF' : 'ALL')
  const [open, setOpen] = useState<string | null>(null)

  const counts: Record<string, number> = {
    ALL: episodes.length,
    DIFF: episodes.filter(changed).length,
  }
  for (const r of ['QUERY', 'OBTAIN', 'RECODE'] as Remedy[]) {
    counts[r] = episodes.filter((e) => topRemedy(e) === r).length
  }

  const shown = episodes.filter((e) =>
    filter === 'ALL'
      ? true
      : filter === 'DIFF'
        ? changed(e)
        : topRemedy(e) === filter,
  )

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
        {((hasDiff
          ? ['DIFF', 'ALL', 'QUERY', 'OBTAIN', 'RECODE']
          : ['ALL', 'QUERY', 'OBTAIN', 'RECODE']) as Filter[]).map((f) => (
          <button
            key={f}
            className={'f' + (filter === f ? ' on' : '') + (f === 'DIFF' ? ' diff' : '')}
            onClick={() => setFilter(f)}
          >
            {f !== 'ALL' && f !== 'DIFF' && (
              <span
                className="sw"
                style={{ background: `var(--${REMEDY[f].css})` }}
              />
            )}
            {f === 'ALL'
              ? 'Daftar berjalan'
              : f === 'DIFF'
                ? 'Berubah sejak sweep terakhir'
                : REMEDY[f].label}
            <span className="n">{counts[f]}</span>
          </button>
        ))}
      </div>

      {filter === 'ALL' && hasDiff && (
        <p className="cnote caveat" style={{ margin: '0 0 10px' }}>
          Ini seluruh temuan yang masih terbuka, termasuk yang sudah muncul
          kemarin. Antrean pagi adalah <b>Berubah sejak sweep terakhir</b>.
        </p>
      )}

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
                {/* Subject first. It is the only token that differs between
                    two rows of the same defect class, and a reader scanning
                    forty rows reads the left edge of each one. The templated
                    sentence follows it and is allowed to repeat. */}
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
                      {e.flags[0]!.subject && (
                        <b className="rsubj mono">{e.flags[0]!.subject}</b>
                      )}
                      <span className="rsent">{e.flags[0]!.rationale}</span>
                      {e.flags.length > 1 && (
                        <span className="rmore">+{e.flags.length - 1}</span>
                      )}
                    </>
                  ) : (
                    <span className="muted">
                      Tidak ada temuan pada pemeriksaan ini
                    </span>
                  )}
                </span>
                <span className="rmeta">
                  {(() => {
                    const m = e.flags
                      .map((f) => marks.get(f.suppression_key))
                      .find(Boolean)
                    return m ? (
                      <span className={'dmark ' + m}>
                        {m === 'escalated' ? '↑ naik' : '● baru'}
                      </span>
                    ) : null
                  })()}
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
                        <b className="rsubj mono">{f.subject}</b>
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
