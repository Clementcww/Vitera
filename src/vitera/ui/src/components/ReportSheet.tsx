import type { IntakePayload } from '../intake'
import { SEVERITY_ID } from '../intake'
import { rp } from '../format'

/* The generated report: what the check found, on one sheet a human signs.
 *
 * It is the browser's rendering of exactly what `make intake` writes as a PDF,
 * from the same exported run, so the screen and the printout cannot say
 * different things.
 *
 * Rule 1 governs the whole component. This is a DRAFT: it is stamped as one on
 * every page, its signature block is empty, and it states in its own body that
 * nothing has been sent to BPJS. A report that could be mistaken for a
 * submission would defeat the point of having a human commit.
 *
 * Rule 7 governs the numbers. `Diajukan`, `Draf perbaikan` and the conditional
 * line are three grouper figures carried through the export untouched. The
 * conditional amount — what would become claimable only if a DPJP documents
 * care the record merely suggests — is printed apart from the total and is
 * never added into it. Nothing on this sheet is arithmetic performed here.
 *
 * Printing works by hiding the app rather than by opening a second window:
 * this is a direct child of `.app`, and the print stylesheet hides its
 * siblings. No popup to be blocked, no second copy of the styles to drift.
 */

const today = () =>
  new Date().toLocaleDateString('id-ID', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  })

export function ReportSheet({
  data,
  onClose,
}: {
  data: IntakePayload
  onClose: () => void
}) {
  const c = data.correction
  const f = data.form
  const gate = data.gate
  if (!c || !f) return null

  const delta = c.total_after_idr - c.total_before_idr
  const conditional = c.total_if_confirmed_idr - c.total_after_idr
  const unread = gate.failures_detail.filter((x) => x.severity === 'needs_human_read')
  const changed = c.corrections.filter((x) => (x.delta_idr ?? 0) !== 0)

  return (
    <div className="reportsheet" role="dialog" aria-label="Internal review report">
      <div className="rtoolbar">
        <b>Internal review report</b>
        <span className="spacer" />
        <button className="act" onClick={onClose}>
          Tutup
        </button>
        <button className="act primary" onClick={() => window.print()}>
          Cetak / simpan PDF
        </button>
      </div>

      <article className="paper">
        <div className="stamp" aria-hidden="true">
          DRAF
        </div>

        <header className="rhd">
          <div>
            <h1>Internal Review of the Claim File</h1>
            <p className="rsub">
              {f.nama_ppk} · Kode PPK {f.kode_ppk} · {f.bulan_pelayanan} ·{' '}
              {f.jenis_pelayanan}
            </p>
          </div>
          <div className="rdate">
            <span>Dicetak</span>
            <b>{today()}</b>
          </div>
        </header>

        <p className="rnote">
          This is a <b>draft</b>. Nothing here has been sent to BPJS and no
          change has been written to the claim of record. It takes effect only
          once the coder and the internal verifier have signed it. Every figure
          in this report is synthetic.
        </p>

        <section>
          <h2>1. Value summary</h2>
          <table className="sum">
            <tbody>
              <tr>
                <td>Claimed on the form</td>
                <td className="num mono">{rp(c.total_before_idr)}</td>
              </tr>
              <tr>
                <td>Setelah pemeriksaan (draf)</td>
                <td className="num mono">{rp(c.total_after_idr)}</td>
              </tr>
              <tr className="delta">
                <td>Selisih</td>
                <td className="num mono">
                  {delta < 0 ? 'turun ' : 'naik '}
                  {rp(Math.abs(delta))}
                </td>
              </tr>
            </tbody>
          </table>
          <p className="cond">
            Berpotensi <b className="mono">{rp(conditional)}</b> lebih tinggi
            if the doctor documents the comorbidities already visible in the
            notes. This conditional figure is <b>not</b> included in the total
            above and must not be claimed before that documentation exists.
          </p>
          <p className="src">
            Every rupiah figure is computed by the INA-CBG grouper. The model
            never
            menghasilkan angka uang.
            {c.advisory && ' Pemeriksaan ini berjalan dalam mode advisory.'}
          </p>
        </section>

        <section>
          <h2>2. Where the file came from</h2>
          <table className="kvtab">
            <tbody>
              <tr>
                <td>Sumber</td>
                <td>
                  Scanned sheets, read by {gate.engine}, {gate.pages} pages
                </td>
              </tr>
              <tr>
                <td>Gerbang validasi</td>
                <td>{gate.passed ? 'Lolos' : 'Ditahan'}</td>
              </tr>
              <tr>
                <td>Baris rincian</td>
                <td>
                  {gate.rows} baris, {Math.round(gate.rows_complete_share * 100)}%
                  read in full, {gate.matched_episodes} matched the record
                  rumah sakit
                </td>
              </tr>
              <tr>
                <td>Kolom formulir</td>
                <td>
                  {gate.fields_read} terbaca
                  {gate.fields_missing.length
                    ? `, gagal: ${gate.fields_missing.join(', ')}`
                    : ''}
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        {changed.length > 0 && (
          <section>
            <h2>3. Episodes whose value changed</h2>
            <table className="rtab">
              <thead>
                <tr>
                  <th>No. SEP</th>
                  <th>Episode</th>
                  <th>INA-CBG diajukan</th>
                  <th>INA-CBG draf</th>
                  <th className="num">Diajukan</th>
                  <th className="num">Draf</th>
                  <th className="num">Selisih</th>
                </tr>
              </thead>
              <tbody>
                {changed.map((x) => (
                  <tr key={x.sep}>
                    <td className="mono">{x.sep}</td>
                    <td className="mono">{x.episode_id}</td>
                    <td className="mono">{x.cbg_before ?? '—'}</td>
                    <td className="mono">{x.cbg_after ?? '—'}</td>
                    <td className="num mono">
                      {x.biaya_before === null ? '—' : rp(x.biaya_before)}
                    </td>
                    <td className="num mono">
                      {x.biaya_after === null ? '—' : rp(x.biaya_after)}
                    </td>
                    <td className="num mono">
                      {x.delta_idr === null ? '—' : rp(x.delta_idr)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        <section>
          <h2>4. Findings, with the record quoted</h2>
          <p className="lead">
            {c.findings_count} findings across {c.episodes} episodes. Each one
            quotes the record word for word. A finding that cannot
            mengutip sudah dibuang oleh sistem sebelum sampai ke sini.
          </p>
          <ol className="finds">
            {c.findings.map((x, i) => (
              <li key={i}>
                <div className="fh">
                  <b>{x.label}</b>
                  <span className={'rtag r-' + x.remedy_code.toLowerCase()}>
                    {x.remedy} — {x.actor}
                  </span>
                  <span className="fid mono">{x.episode_id}</span>
                </div>
                <blockquote>{x.quote}</blockquote>
              </li>
            ))}
          </ol>
        </section>

        {unread.length > 0 && (
          <section>
            <h2>5. Values a person must re-read</h2>
            <p className="lead">
              The machine was not confident of these values. None became a
              claim finding; each waits for someone to check the original sheet.
            </p>
            <ul className="reads">
              {unread.map((x, i) => (
                <li key={i}>
                  <span className={'sev ' + SEVERITY_ID[x.severity].css}>
                    {SEVERITY_ID[x.severity].label}
                  </span>
                  {x.detail}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="signs">
          <h2>Persetujuan</h2>
          <p className="lead">
            This draft has no effect and is not submitted until both columns
            bawah ditandatangani.
          </p>
          <div className="signrow">
            <div>
              <span>Coder</span>
              <div className="line" />
            </div>
            <div>
              <span>Internal verifier</span>
              <div className="line" />
            </div>
          </div>
        </section>

        <footer className="rfoot">
          Vitera · internal review draft · not sent to BPJS · synthetic data
        </footer>
      </article>
    </div>
  )
}
