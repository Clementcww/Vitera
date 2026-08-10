/* The dark card, on the landing.
 *
 * It used to be a teaser for the morning queue, which was redundant: the card
 * BECOMES the queue when you enter the workbench, so the landing was spending
 * its only dark surface describing what the next click would show. It now says
 * what Vitera is, and opens onto the problem it exists for.
 *
 * Closed, it is three lines. Open, it covers the bento the same way the accent
 * card does, and holds the two gaps from the design brief.
 *
 * The numbers in there describe THE PROBLEM, not results of ours, and the card
 * says so in its own footer rather than in a caption nobody reads. That
 * distinction is the one thing on this screen that would cost us the paper if
 * it blurred: `docs/CLAIMS.md` permits us to state the size of the problem and
 * forbids us to state it as something Vitera recovers.
 *
 * `source` must name the study, or say plainly that the line is our estimate.
 * It previously read "angka masalah dari literatur" under a figure that traced
 * to a vendor blog (grade D) — claiming a provenance the number did not have,
 * which is worse than no source line at all. `docs/LITERATURE.md` grades every
 * source and lists what we may not state; the two figures here are the grade-A
 * ones it tells us to lead with. If you add a figure, it goes in `PROBLEM` with
 * a `source` that survives that file, or it does not go in.
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
    stat: '12-17%',
    statIsFigure: true,
    statNote: 'klaim rawat inap yang pending, dan itu hanya yang terlihat',
    body:
      'Pending adalah ujung yang tampak. Prevalensi kesalahan pada studi ' +
      'rawat inap Indonesia berjalan jauh di atas angka pending, sehingga ' +
      'sebagian besar kesalahan tidak pernah pending sama sekali: ia terserap ' +
      'diam-diam sebagai kurang bayar dan tidak pernah muncul di statistik ' +
      'siapa pun. Di rumah sakit dengan volume ribuan klaim per bulan, unit ' +
      'casemix yang berisi beberapa orang tidak mungkin menelaah seluruhnya ' +
      'sebelum berkas dikirim.',
    source:
      'Pending 12,2% (Maulida & Djunawan 2022, n=720) dan 16,7% (Dewi & ' +
      'Wirajaya 2024, n=779), keduanya rawat inap, single-site. Belum ada ' +
      'angka nasional yang dipublikasikan. Keterbatasan kapasitas telaah ' +
      'adalah perkiraan kami dari aritmetika staf, bukan angka terukur.',
  },
  {
    key: 'waktu',
    head: 'Celah waktu',
    stat: 'Setelah pulang',
    statIsFigure: false,
    statNote: 'kapan pemeriksaan yang ada baru terjadi',
    body:
      'Pada 68,6% episode rawat inap yang diperiksa, diagnosis sekunder yang ' +
      'ada di rekam medis tidak terbawa ke resume medis. Pemeriksaan yang ' +
      'sempat dilakukan baru terjadi setelah pasien pulang, saat hal seperti ' +
      'itu sudah tidak bisa diperbaiki: penunjang tidak bisa diminta untuk ' +
      'pasien yang sudah di rumah, dan DPJP yang diminta melengkapi ' +
      'dokumentasi beberapa hari kemudian sedang menyusun ulang dari ingatan.',
    source:
      'Opitasari & Nurwahyuni 2018, HSJI 9(1):14-18, Tabel 2 (n=105 rekam ' +
      'medis rawat inap BPJS, di-recode ulang oleh koder standar Kemenkes). ' +
      'Urutan telaah pasca-pulang adalah pengamatan alur kerja kami.',
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
              Angka di atas menggambarkan besar masalahnya, bukan hasil
              pengukuran Vitera. Yang berasal dari publikasi disebut studinya;
              yang merupakan perkiraan kami ditandai sebagai perkiraan. Yang
              kami ukur ada di kartu oranye dan di dasbor unit.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
