import type { Group, Remedy } from './types'

/* Formatting. The only rule that matters here is architectural rule 7: the
 * grouper is authoritative for tariff, and the model never produces a monetary
 * figure. So this file formats rupiah — it never computes one, and an
 * UNGROUPABLE episode renders a dash rather than an estimate. */

export const rp = (n: number) => 'Rp ' + n.toLocaleString('id-ID')

export const jt = (n: number) =>
  'Rp ' + (n / 1e6).toFixed(2).replace('.', ',') + ' jt'

/** Never estimate. `UNGROUPABLE` has no tariff and must not acquire one here. */
export function tariff(g: Group): string {
  return g.tariff_idr === null ? '—' : rp(g.tariff_idr)
}

export const REMEDY: Record<Remedy, { label: string; who: string; css: string }> = {
  QUERY: {
    label: 'Query',
    who: 'DPJP, perlu pasien masih di ruangan',
    css: 'query',
  },
  OBTAIN: {
    label: 'Obtain',
    who: 'Petugas berkas, masih bisa setelah pulang',
    css: 'obtain',
  },
  RECODE: {
    label: 'Recode',
    who: 'Koder, masih bisa sampai submit',
    css: 'recode',
  },
}

/* Defect-class labels for the screen.
 *
 * `DefectClass.label` in contracts.py is English — it is read by us, by the
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
