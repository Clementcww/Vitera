import { useState } from 'react'
import type { ReactNode } from 'react'
import type { EpisodeView, Remedy, SweepPayload } from '../types'
import { DEFECT_ID, NONE, REMEDY, jt } from '../format'
import { queueOrder } from '../data'
import { Term } from './Term'

/* L0 and L1.
 *
 * The koder does 30–50 claims a day. The screen's job is to let them skip
 * fast, so a row is one line until asked: who acts, how much window is left,
 * how much is recoverable. Findings appear on expand; the workbench is a
 * second click.
 *
 * Rupiah come from the grouper and are badged as such. An episode the grouper
 * could not group shows a dash, never an estimate (rule 7).
 *
 * ── Two things here were fixed after watching the screen rather than reading
 * it, and both were the same mistake: a row whose distinguishing information
 * was not at its left edge.
 *
 * The row title used to open with the rationale, on the theory that naming the
 * actual code beat repeating the defect class. But the rationale is a template
 * (thirteen of forty-seven findings share one) so eleven consecutive rows
 * read "bukti klinis untuk … ada pada catatan, namun diagnosis tidak tertulis"
 * with the only varying token, the ICD code, buried mid-sentence. The subject
 * now leads and the sentence follows it.
 *
 * The `Baru`/`Naik` marks come from the sweep's diff. Without them the queue is
 * a standing list that looks identical every morning, which is precisely the
 * monitoring product that gets switched off in week two (sweep rule 3). The
 * default filter is what CHANGED since the last sweep; the standing list is one
 * click away and clearly labelled as such.
 *
 * `grouped` is the demo's before-and-after, and it governs three things at
 * once because all three are the same thing: **triage**.
 *
 *     order    registry order until swept, `queueOrder` after
 *     colour   one neutral dot until swept, the actor's colour after
 *     filters  absent until swept
 *
 * Un-swept the screen is a work list: every finding the pipeline produced, by
 * episode number, with nothing saying which to touch first. That is what a
 * casemix unit has today and it is the comparison we are arguing against.
 *
 * Read the boundary carefully before moving any of it. The sweep does **not**
 * decide remedy: `_classify` in the cross-encoder does, deterministically, and
 * the value is sitting in the payload the whole time. What the sweep does is
 * *stage a queue* out of that, which is ordering, grouping and the diff, and
 * per the design brief's build order that is exactly its scope. So the colour appears
 * with the sweep because the triage does, not because the remedy did. The
 * caption below says that in as many words, and it needs to keep saying it. */

type Filter = 'ALL' | 'DIFF' | Remedy
type DiffMark = 'new' | 'escalated' | null

function topRemedy(e: EpisodeView): Remedy | null {
  if (!e.flags.length) return null
  return e.flags.reduce((a, b) => (a.decay_rank <= b.decay_rank ? a : b)).remedy
}

/** What each episode's MOST RECENT sweep reported as new or escalated.
 *
 * Per episode, not per calendar night. The workbench shows each episode on its
 * own current day, some mid-stay and some at discharge, so "what changed" has
 * to mean *at that episode's last sweep*. Reading one shared night instead
 * marks nothing for every episode that discharged earlier in the week, and
 * marks nothing at all on a night where the whole ward happened to be quiet.
 *
 * Keyed on `suppression_key` (class, subject and evidence hash) because that
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
  grouped = false,
  controls,
}: {
  episodes: EpisodeView[]
  sweep?: SweepPayload | null
  onOpen: (id: string) => void
  /** Arrange the rows under the actor who has to fix them. Set by the sweep. */
  grouped?: boolean
  /** The demo strip. Passed in rather than imported so this file keeps knowing
   *  only about the queue. */
  controls?: ReactNode
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

  /* Registry order until the sweep stages a queue, then the queue's order.
     `episodes` arrives sorted by episode id from `load`; the copy is so the
     sort does not mutate the payload other screens are reading. */
  const listed = grouped ? [...episodes].sort(queueOrder) : episodes

  const shown = listed.filter((e) =>
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

      {controls}

      {/* Filters are triage too: every one of them is a cut the sweep's output
          defines. Un-swept there is nothing to cut by, so the bar is absent
          rather than present and inert. */}
      {grouped && (
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
      )}

      {filter === 'ALL' && hasDiff && (
        <p className="cnote caveat" style={{ margin: '0 0 10px' }}>
          Ini seluruh temuan yang masih terbuka, termasuk yang sudah muncul
          kemarin. Antrean pagi adalah <b>Berubah sejak sweep terakhir</b>.
        </p>
      )}

      {/* Before the sweep the screen is honest about being just a list, and
          about WHY it is only a list. The second sentence is the one that
          keeps this from overclaiming: the remedy is already in the payload,
          decided by the cross-encoder; what is missing is the triage. */}
      {!grouped && (
        <p className="cnote" style={{ margin: '0 0 10px' }}>
          {episodes.length} episode, urut nomor, belum ditriase. Setiap temuan
          sudah punya pelaku dan jendela perbaikannya sendiri, tetapi yang
          menyusunnya jadi antrean, yaitu urutan, pengelompokan dan penandaan
          apa yang berubah semalam, adalah sweep.
        </p>
      )}

      {/* One row renderer for both arrangements. Grouping must not be able to
          change what a row says, only where it sits. */}
      {(() => {
        const row = (e: EpisodeView) => {
          const rm = topRemedy(e)
          const expanded = open === e.episode_id
          const delta = e.money.delta_idr
          return (
            <div className={'row' + (expanded ? ' open' : '')} key={e.episode_id}>
              <button
                className="rsum"
                onClick={() => setOpen(expanded ? null : e.episode_id)}
              >
                {/* One neutral dot until the queue is triaged. The remedy is
                    known either way; what the colour encodes is a queue
                    position, and un-swept there is no queue. */}
                <span
                  className="rdot"
                  style={{
                    background:
                      grouped && rm ? `var(--${REMEDY[rm].css})` : 'var(--mid)',
                  }}
                  title={
                    !grouped
                      ? 'belum ditriase'
                      : rm
                        ? REMEDY[rm].label
                        : 'tidak ada temuan'
                  }
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
                      {NONE}
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
        }

        if (!grouped) {
          return <div className="list">{shown.map(row)}</div>
        }

        /* Grouped: one section per actor, in repair-window order, then the
           episodes the pipeline found nothing on. A group with no rows is
           omitted rather than shown empty, so a filtered view does not leave
           three headings hanging over nothing. */
        const order: Remedy[] = ['QUERY', 'OBTAIN', 'RECODE']
        const clean = shown.filter((e) => topRemedy(e) === null)

        return (
          <>
            {order.map((r) => {
              const rows = shown.filter((e) => topRemedy(e) === r)
              if (!rows.length) return null
              return (
                <section className="qgroup" key={r}>
                  <h2 className="ghead">
                    <span
                      className="sw"
                      style={{ background: `var(--${REMEDY[r].css})` }}
                    />
                    {REMEDY[r].label}
                    <span className="gwho">{REMEDY[r].who}</span>
                    <span className="n">{rows.length}</span>
                  </h2>
                  <div className="list">{rows.map(row)}</div>
                </section>
              )
            })}
            {clean.length > 0 && (
              <section className="qgroup">
                <h2 className="ghead">
                  <span className="sw" style={{ background: 'var(--mid)' }} />
                  Tidak perlu tindakan
                  <span className="gwho">
                    Pemeriksaan selesai, tidak ada temuan terbuka
                  </span>
                  <span className="n">{clean.length}</span>
                </h2>
                <div className="list">{clean.map(row)}</div>
              </section>
            )}
          </>
        )
      })()}

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
