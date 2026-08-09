import { useMemo, useState } from 'react'
import type { IntakePayload, ReadField } from '../intake'
import { FIELD_ID, SEVERITY_ID, band } from '../intake'
import { rp } from '../format'
import { Term } from './Term'

/* The scanned FPK, with the machine's reading drawn on top of it.
 *
 * This exists because paper intake makes one claim that is easy to assert and
 * hard to believe: *the machine read this value, out of this rectangle, this
 * confidently*. The only honest way to present that is to show the paper and
 * the rectangle together.
 *
 * Three decisions that are not cosmetic:
 *
 * - **Every observation can be shown, not only the ones a field used.** A view
 *   that drew only the successful reads would hide the failures, which is the
 *   half a koder needs. The default is fields-only for legibility; one toggle
 *   shows everything the engine saw.
 * - **Cells the reader could not get are marked, never blank.** A blank in a
 *   rupiah column reads as a zero. `tidak terbaca` reads as what it is.
 * - **The gate's verdict sits above the data, not below it.** If the sheet was
 *   held, nothing downstream ran, and that has to be the first thing on screen
 *   rather than a footnote under a table of numbers.
 */

type Mode = 'fields' | 'all'

export function ScanView({
  data,
  onReport,
}: {
  data: IntakePayload
  onReport: () => void
}) {
  const [page, setPage] = useState(0)
  const [mode, setMode] = useState<Mode>('fields')
  const [focus, setFocus] = useState<string | null>(null)

  const p = data.pages[Math.min(page, data.pages.length - 1)]
  const fieldsHere = useMemo(
    () => (p ? data.fields.filter((f) => f.page === p.index) : []),
    [data.fields, p],
  )
  const gate = data.gate
  const held = !gate.passed

  if (!p) {
    return (
      <section className="view">
        <h1>Berkas pindaian</h1>
        <p className="lede">
          Tidak ada halaman pindaian pada ekspor ini. Jalankan{' '}
          <code>make ui-intake</code>.
        </p>
      </section>
    )
  }

  return (
    <section className="view">
      <h1>Berkas pindaian</h1>
      <p className="lede">
        Lembar <Term k="fpk">FPK</Term> yang dipindai, dengan hasil bacaan mesin
        digambar di atasnya. Kotak adalah posisi asli tempat setiap nilai
        ditemukan, bukan gambar ulang.
      </p>

      <div className={'gatebar ' + (held ? 'held' : 'ok')}>
        <span className="gdot" />
        <b>{held ? 'Berkas ditahan di gerbang validasi' : 'Lolos gerbang validasi'}</b>
        <span className="gsub">
          {gate.engine} · {gate.rows} baris rincian ·{' '}
          {Math.round(gate.rows_complete_share * 100)}% terbaca lengkap ·{' '}
          {gate.matched_episodes} cocok dengan rekam rumah sakit
        </span>
        {!held && (
          <button className="act primary gbtn" onClick={onReport}>
            Buat laporan
          </button>
        )}
      </div>

      <details className="help" style={{ margin: '0 0 16px' }}>
        <summary>Apa yang sedang dilihat di sini?</summary>
        <div className="detail">
          Rumah sakit mengirim klaim dengan formulir kertas. Vitera memindai
          formulir itu, membaca isinya, lalu mencocokkannya dengan rekam medis
          sebelum apa pun diproses. Warna kotak menunjukkan seberapa yakin mesin
          membaca: <b className="c-ok">hijau</b> yakin,{' '}
          <b className="c-soft">kuning</b> ragu, <b className="c-weak">merah</b>{' '}
          nyaris tidak terbaca. Nilai yang gagal dibaca ditandai{' '}
          <i>tidak terbaca</i> dan tidak pernah ditebak. Pembacaan yang meragukan
          tidak pernah dijadikan temuan klaim; ia dikembalikan untuk dibaca
          ulang manusia.
        </div>
      </details>

      <div className="scanwrap">
        <div className="scanpane">
          <div className="scanbar">
            {data.pages.map((pg, i) => (
              <button
                key={pg.index}
                className={'f' + (i === page ? ' on' : '')}
                onClick={() => setPage(i)}
              >
                Halaman {i + 1}
              </button>
            ))}
            <span className="spacer" />
            <button
              className={'f' + (mode === 'fields' ? ' on' : '')}
              onClick={() => setMode('fields')}
            >
              Kolom terbaca
            </button>
            <button
              className={'f' + (mode === 'all' ? ' on' : '')}
              onClick={() => setMode('all')}
            >
              Semua bacaan <span className="n">{p.obs.length}</span>
            </button>
          </div>

          <div className="sheet" style={{ aspectRatio: `${p.w} / ${p.h}` }}>
            <img src={p.src} alt={`Lembar pindaian halaman ${page + 1}`} />
            {mode === 'all' &&
              p.obs.map((o, i) => (
                <span
                  key={i}
                  className={'ob b-' + band(o.c)}
                  title={`${o.t}  ·  ${o.c.toFixed(2)}`}
                  style={{
                    left: `${o.x * 100}%`,
                    top: `${o.y * 100}%`,
                    width: `${o.w * 100}%`,
                    height: `${o.h * 100}%`,
                  }}
                />
              ))}
            {mode === 'fields' &&
              fieldsHere.map((f) => (
                <span
                  key={f.name}
                  className={
                    'ob b-' + band(f.confidence) + (focus === f.name ? ' focus' : '')
                  }
                  title={`${FIELD_ID[f.name] ?? f.name}: ${f.value}`}
                  onMouseEnter={() => setFocus(f.name)}
                  onMouseLeave={() => setFocus(null)}
                  style={{
                    left: `${f.bbox[0] * 100}%`,
                    top: `${f.bbox[1] * 100}%`,
                    width: `${(f.bbox[2] - f.bbox[0]) * 100}%`,
                    height: `${(f.bbox[3] - f.bbox[1]) * 100}%`,
                  }}
                />
              ))}
          </div>

          <p className="scannote prose">{data.generated.note}</p>
        </div>

        <div className="scanside">
          <FieldList
            fields={data.fields}
            missing={data.missing}
            focus={focus}
            onFocus={(n) => {
              const f = data.fields.find((x) => x.name === n)
              if (f) setPage(f.page)
              setMode('fields')
              setFocus(n)
            }}
          />

          {gate.failures_detail.length > 0 && (
            <div className="panel" style={{ marginTop: 16 }}>
              <div className="phd">
                <b>Catatan gerbang</b>
                <span className="c">{gate.failures_detail.length}</span>
              </div>
              <ul className="gatelist">
                {gate.failures_detail.slice(0, 14).map((f, i) => (
                  <li key={i}>
                    <span className={'sev ' + SEVERITY_ID[f.severity].css}>
                      {SEVERITY_ID[f.severity].label}
                    </span>
                    <span className="gd">{f.detail}</span>
                  </li>
                ))}
                {gate.failures_detail.length > 14 && (
                  <li className="gmore">
                    dan {gate.failures_detail.length - 14} lainnya
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>
      </div>

      <Rincian data={data} />
    </section>
  )
}

function FieldList({
  fields,
  missing,
  focus,
  onFocus,
}: {
  fields: ReadField[]
  missing: string[]
  focus: string | null
  onFocus: (name: string) => void
}) {
  return (
    <div className="panel">
      <div className="phd">
        <b>Kolom formulir</b>
        <span className="c">
          {fields.length} terbaca{missing.length ? `, ${missing.length} gagal` : ''}
        </span>
      </div>
      <ul className="fieldlist">
        {fields.map((f) => (
          <li
            key={f.name}
            className={focus === f.name ? 'on' : ''}
            onMouseEnter={() => onFocus(f.name)}
          >
            <span className="fn">{FIELD_ID[f.name] ?? f.name}</span>
            <span className="fv">{f.value}</span>
            <span className={'cf b-' + band(f.confidence)} title="keyakinan mesin">
              {f.confidence.toFixed(2)}
            </span>
          </li>
        ))}
        {missing.map((m) => (
          <li key={m} className="gone">
            <span className="fn">{FIELD_ID[m] ?? m}</span>
            <span className="fv">tidak terbaca</span>
            <span className="cf b-weak">—</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Rincian({ data }: { data: IntakePayload }) {
  const [all, setAll] = useState(false)
  const rows = all ? data.lines : data.lines.slice(0, 12)
  const t = data.totals

  return (
    <div className="panel" style={{ marginTop: 18 }}>
      <div className="phd">
        <b>Rincian yang terbaca</b>
        <span className="c">
          {data.lines.length} baris · jumlah pada formulir{' '}
          {t.biaya_idr === null ? '—' : rp(t.biaya_idr)}
        </span>
      </div>
      <div className="tablewrap">
        <table className="rtab">
          <thead>
            <tr>
              <th>No.</th>
              <th>No. SEP</th>
              <th>Episode</th>
              <th>Tgl masuk</th>
              <th>Hari</th>
              <th>INA-CBG</th>
              <th className="num">Biaya</th>
              <th className="num">Yakin</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((ln) => (
              <tr key={ln.index} className={ln.unread.length ? 'partial' : ''}>
                <td className="mono">{ln.index}</td>
                <td className="mono">{ln.sep ?? <i>tidak terbaca</i>}</td>
                <td className="mono dim">{ln.episode_id ?? '—'}</td>
                <td className="mono">{ln.tanggal ?? <i>tidak terbaca</i>}</td>
                <td className="mono">{ln.hari ?? <i>tidak terbaca</i>}</td>
                <td className="mono">{ln.cbg ?? <i>tidak terbaca</i>}</td>
                <td className="mono num">
                  {ln.biaya_idr === null ? <i>tidak terbaca</i> : rp(ln.biaya_idr)}
                </td>
                <td className={'mono num cf b-' + band(ln.confidence)}>
                  {ln.confidence.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.lines.length > 12 && (
        <button className="open-btn" style={{ margin: 12 }} onClick={() => setAll(!all)}>
          {all ? 'Tampilkan 12 teratas' : `Tampilkan semua ${data.lines.length} baris`}
        </button>
      )}
    </div>
  )
}
