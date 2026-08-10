import type { Group, Remedy } from './types'

/* Formatting. The only rule that matters here is architectural rule 7: the
 * grouper is authoritative for tariff, and the model never produces a monetary
 * figure. So this file formats rupiah; it never computes one, and an
 * UNGROUPABLE episode renders a dash rather than an estimate. */

export const rp = (n: number) => 'Rp ' + n.toLocaleString('id-ID')

export const jt = (n: number) =>
  'Rp ' + (n / 1e6).toFixed(2).replace('.', ',') + ' jt'

/** Never estimate. `UNGROUPABLE` has no tariff and must not acquire one here. */
/** What a cell shows when a value CANNOT be computed.
 *
 * Load-bearing, not decoration: architectural rule 7 forbids estimating a
 * tariff when the grouper returns UNGROUPABLE, so this glyph is the visible
 * form of "we do not know". It is deliberately distinct from the `·` used for
 * a value that IS known and happens to be zero.
 *
 * One constant so the mark is one edit away. It was an em dash; en dash now,
 * per the house rule against em dashes anywhere on the screen. */
export const NONE = '\u2013'

export function tariff(g: Group): string {
  return g.tariff_idr === null ? NONE : rp(g.tariff_idr)
}

/* `label` is an instruction, not the enum name.
 *
 * QUERY / OBTAIN / RECODE are our vocabulary, not the koder's, and a screen
 * that shows them is asking the reader to learn a taxonomy before they can act.
 * `who` carries the deadline, because remedy is the thing that decides how fast
 * the repair window shuts. */
export const REMEDY: Record<Remedy, { label: string; who: string; css: string }> = {
  QUERY: {
    label: 'Tanya DPJP',
    who: 'DPJP, perlu pasien masih di ruangan',
    css: 'query',
  },
  OBTAIN: {
    label: 'Lengkapi berkas',
    who: 'Petugas berkas, masih bisa setelah pulang',
    css: 'obtain',
  },
  RECODE: {
    label: 'Perbaiki kode',
    who: 'Koder, masih bisa sampai submit',
    css: 'recode',
  },
}

/* Defect-class labels for the screen.
 *
 * `DefectClass.label` in contracts.py is English, read by us and by the
 * paper and by the judges. The koder is Indonesian and reads this, so the
 * user-facing wording lives here rather than being pushed back into a contract
 * that four other modules code against.
 *
 * Wording rule from CLAUDE.md: never tell a clinician what to write. Every
 * label below states what the RECORD does not show, not what the doctor should
 * have done. */
export const DEFECT_ID: Record<string, string> = {
  D1: 'Berkas klaim tidak lengkap',
  D2: 'Spesifisitas kode kurang, ada kode saudara',
  D3: 'Diagnosis tidak didukung narasi rekam medis',
  D4: 'Komorbiditas terbaca di catatan, belum terdokumentasi',
  D5: 'Pemeriksaan penunjang belum dilampirkan',
  D6: 'Prosedur tidak koheren dengan diagnosis',
  D7: 'Pola penambahan komorbiditas tanpa bukti',
  D8: 'Ketidakcocokan administratif (SEP, identitas, tanggal)',
}

export const VERDICT: Record<string, string> = {
  clean: 'Tidak ada temuan',
  flagged: 'Perlu perbaikan',
  abstain: 'Perlu penilaian koder',
}

export const SOURCE: Record<string, string> = {
  rules: 'aturan',
  cross_encoder: 'cross-encoder',
  router: 'router',
}
