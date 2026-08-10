/* The dark card, on the landing.
 *
 * It used to be a teaser for the morning queue, which was redundant: the card
 * BECOMES the queue when you enter the workbench, so the landing was spending
 * its only dark surface describing what the next click would show. It now says
 * what Vitera is, and opens onto the problem it exists for.
 *
 * Closed, it is three lines. Open, it covers the bento the same way the accent
 * card does, and holds the two gaps from CLAUDE.md.
 *
 * The numbers in there are PUBLISHED FINDINGS ABOUT THE PROBLEM, not results
 * of ours, and the card says so in its own footer rather than in a caption
 * nobody reads. That distinction is the one thing on this screen that would
 * cost us the paper if it blurred: `docs/CLAIMS.md` permits us to state the
 * size of the problem and forbids us to state it as something Vitera recovers.
 * If you add a figure here, it goes in `PROBLEM` with its own `source` line, or
 * it does not go in.
 */

const PROBLEM: {
  key: string
  head: string
  stat: string
  /** Figures get the mono face, words do not. A phrase set in the number face
   *  reads as a measurement, and only one of these two is one. */
  statIsFigure: boolean
  statNote: string
  body: string
  source: string
}[] = [
  {
    key: 'cakupan',
    head: 'Celah cakupan',
    stat: '5-15%',
    statIsFigure: true,
    statNote: 'klaim yang sempat diperiksa sebelum dikirim',
    body:
      'Di rumah sakit dengan lebih dari 1.000 klaim per bulan, unit casemix ' +
      'berisi 2 sampai 5 orang memeriksa 30 sampai 50 klaim sehari. Sisanya, ' +
      '85 sampai 95 persen, berangkat tanpa diperiksa dan pending di kisaran ' +
      '15 persen.',
    source: 'angka masalah dari literatur, bukan hasil ukur Vitera',
  },
  {
    key: 'waktu',
    head: 'Celah waktu',
    stat: 'Setelah pulang',
    statIsFigure: false,
    statNote: 'kapan pemeriksaan yang ada baru terjadi',
    body:
      'Pemeriksaan yang sempat dilakukan terjadi setelah pasien pulang, saat ' +
      'banyak masalah sudah tidak bisa diperbaiki. Pemeriksaan penunjang ' +
      'tidak bisa diminta untuk pasien yang sudah di rumah, dan DPJP yang ' +
      'diminta melengkapi dokumentasi beberapa hari kemudian sedang menyusun ' +
      'ulang dari ingatan.',
    source: 'alur kerja rumah sakit, langkah 7 pada diagram verifikasi internal',
  },
]

export function About({
  expanded,
  onExpand,
}: {
  expanded: boolean
  onExpand: (open: boolean) => void
}) {
  return (
    <div className={'teaser about' + (expanded ? ' open' : '')}>
      <div className="rings" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>

      <div className="abouthd">
        <h2>
          About
          <br />
          Vitera
        </h2>
        {expanded && (
          <button
            className="closebtn"
            onClick={() => onExpand(false)}
            aria-label="Tutup"
          >
            ×
          </button>
        )}
      </div>

      {!expanded && (
        <>
          <p className="aboutlede">
            Kami menguji klaim sebelum BPJS melakukannya, selagi catatannya
            masih bisa diperbaiki.
          </p>
          <div className="aboutfoot">
            <button className="aboutmore" onClick={() => onExpand(true)}>
              Permasalahan yang kami hadapi <span aria-hidden="true">→</span>
            </button>
          </div>
        </>
      )}

      {expanded && (
        <div className="aboutwrap">
          <div className="aboutsheet">
            <p className="aboutkicker">Permasalahan yang kami hadapi</p>
            <h3 className="aboutbig">
              Dua celah, bukan satu. Menutup salah satunya saja tidak menutup
              apa pun.
            </h3>

            <div className="probgrid">
              {PROBLEM.map((p) => (
                <section key={p.key} className="probcard">
                  <h4>{p.head}</h4>
                  <b className={'probstat' + (p.statIsFigure ? ' mono' : '')}>
                    {p.stat}
                  </b>
                  <span className="probnote">{p.statNote}</span>
                  <p className="prose">{p.body}</p>
                  <p className="probsrc">{p.source}</p>
                </section>
              ))}
            </div>

            <p className="aboutclose prose">
              Vitera menutup keduanya dengan satu cara: pipeline yang sama
              dijalankan tiap malam untuk tiap episode yang masih dirawat, lalu
              yang masuk antrean hanyalah selisihnya, yaitu apa yang hari ini
              benar dan kemarin belum.
            </p>

            {/* The line that keeps the claims register honest. It is here, in
                the same type size as the rest, not in a caption. */}
            <p className="aboutsrc">
              Angka di atas menggambarkan besar masalahnya dan berasal dari
              publikasi serta praktik lapangan. Itu bukan hasil pengukuran
              Vitera. Yang kami ukur ada di kartu oranye dan di dasbor unit.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
