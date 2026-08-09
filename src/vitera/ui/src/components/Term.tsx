/* Plain-language glossary, inline.
 *
 * The koder knows every one of these words; a judge, an investor or a member
 * of the public does not, and the UI has to hold both audiences without
 * splitting into two apps. So domain terms render with a dotted underline and
 * a one-sentence definition on hover/focus — written in plain Bahasa, defining
 * the thing, never marketing it.
 *
 * Native `title` plus a visible affordance, no tooltip library: it works on
 * every device the demo might run on, costs nothing when ignored, and the
 * koder who already knows the words never has to interact with it.
 */

const GLOSSARY: Record<string, string> = {
  bpjs: 'BPJS Kesehatan — asuransi kesehatan nasional Indonesia. Rumah sakit menagih biaya perawatan ke BPJS lewat klaim.',
  klaim:
    'Tagihan rumah sakit ke BPJS atas perawatan satu pasien. Jika dokumennya tidak lengkap atau kodenya salah, klaim dikembalikan dan pembayaran tertunda.',
  'klaim-pending':
    'Klaim yang dikembalikan BPJS karena ada masalah — rumah sakit harus memperbaiki dan mengirim ulang, pembayaran tertunda berminggu-minggu.',
  koder:
    'Petugas rumah sakit yang menerjemahkan catatan dokter menjadi kode diagnosis standar. Pengguna utama aplikasi ini.',
  dpjp: 'Dokter Penanggung Jawab Pelayanan — dokter yang merawat pasien dan menulis ringkasan medisnya.',
  sep: 'Surat Eligibilitas Peserta — surat jaminan BPJS yang diterbitkan saat pasien masuk rawat inap.',
  cbg: 'Kelompok tarif INA-CBG. Setiap kombinasi diagnosis masuk ke satu kelompok dengan tarif paket tetap — kode yang salah berarti tarif yang salah.',
  grouper:
    'Perangkat lunak deterministik yang menghitung kelompok tarif dari kode diagnosis. Satu-satunya sumber angka rupiah di aplikasi ini — model AI tidak pernah menghasilkan angka uang.',
  'resume-medis':
    'Ringkasan perawatan yang ditulis dokter saat pasien pulang. Dokumen utama yang diperiksa BPJS.',
  cppt: 'Catatan perkembangan harian pasien — ditulis setiap hari selama dirawat.',
  'rekam-medis':
    'Seluruh catatan perawatan pasien: catatan harian, hasil laboratorium, daftar obat, ringkasan pulang.',
  komorbiditas:
    'Penyakit penyerta di samping diagnosis utama — misalnya diabetes pada pasien pneumonia. Jika tidak tertulis di dokumen, BPJS tidak membayarnya.',
  abstain:
    'Sistem menyatakan tidak yakin dan menyerahkan penilaian ke manusia — bukan menebak. Kejujuran ini disengaja dan diukur.',
  advisory:
    'Mode saat lapisan AI mati: hanya pemeriksaan aturan sederhana yang berjalan, dan sistem mengatakannya terang-terangan.',
  'cross-encoder':
    'Model AI kecil (dijalankan di rumah sakit, bukan di cloud) yang menilai satu hal saja: apakah catatan medis mendukung kode yang ditulis.',
  verbatim:
    'Kutipan kata demi kata dari dokumen asli. Temuan tanpa kutipan asli otomatis dibuang oleh sistem.',
}

export function Term({ k, children }: { k: string; children: React.ReactNode }) {
  const def = GLOSSARY[k]
  if (!def) return <>{children}</>
  return (
    <span className="term" tabIndex={0} title={def}>
      {children}
    </span>
  )
}

export { GLOSSARY }
