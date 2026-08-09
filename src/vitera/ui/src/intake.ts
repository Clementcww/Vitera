/* Types and loader for the scanned-FPK view.
 *
 * Mirrors `src/vitera/intake/export_ui.py`. Kept out of `types.ts` because
 * intake is optional: the workbench runs perfectly without it, and a judge who
 * has not run `make ui-intake` should get a tab that explains itself rather
 * than a screen that fails to load.
 *
 * Nothing here derives a value. The boxes drawn on the page image are the OCR's
 * own coordinates, the confidences are the engine's, and every rupiah figure
 * came from the grouper before it was written to this file. The view's whole
 * claim is "the machine read this, from here" — recomputing any part of it in
 * the browser would make that claim decorative.
 */

export interface Obs {
  t: string
  c: number
  x: number
  y: number
  w: number
  h: number
}

export interface ScanPage {
  index: number
  src: string
  w: number
  h: number
  obs: Obs[]
}

export interface ReadField {
  name: string
  value: string
  confidence: number
  anchor_similarity: number
  suspect: boolean
  page: number
  bbox: [number, number, number, number]
}

export interface ReadLine {
  index: number
  sep: string | null
  episode_id: string | null
  nama: string | null
  kartu: string | null
  tanggal: string | null
  hari: number | null
  cbg: string | null
  biaya_idr: number | null
  confidence: number
  unread: string[]
}

export type Severity = 'blocking' | 'advisory' | 'needs_human_read'

export interface GateFailure {
  check: string
  detail: string
  severity: Severity
  subject: string | null
}

export interface Gate {
  passed: boolean
  engine: string
  pages: number
  fields_read: number
  fields_missing: string[]
  mean_field_confidence: number
  rows: number
  rows_complete_share: number
  matched_episodes: number
  unmatched_sep: string[]
  failures: Record<string, number>
  failures_detail: GateFailure[]
}

export interface Finding {
  episode_id: string
  sep: string
  episode: string
  defect_class: string
  label: string
  remedy: string
  remedy_code: string
  actor: string
  quote: string
  doc_id?: string
  score?: number
}

export interface CorrectionRow {
  sep: string
  episode_id: string
  cbg_before: string | null
  cbg_after: string | null
  biaya_before: number | null
  biaya_after: number | null
  biaya_if_confirmed: number | null
  delta_idr: number | null
  flags: number
}

export interface Correction {
  episodes: number
  findings_count: number
  advisory: boolean
  errors: string[]
  total_before_idr: number
  total_after_idr: number
  total_if_confirmed_idr: number
  source: 'grouper'
  corrections: CorrectionRow[]
  findings: Finding[]
}

export interface IntakePayload {
  generated: {
    engine: string
    profile: string
    seed: number
    scan_dir: string
    note: string
  }
  pages: ScanPage[]
  fields: ReadField[]
  missing: string[]
  totals: { kasus: number | null; hari: number | null; biaya_idr: number | null }
  lines: ReadLine[]
  gate: Gate
  form: {
    cabang: string
    nama_ppk: string
    kode_ppk: string
    bulan_pelayanan: string
    jenis_pelayanan: string
    kasus: number
    hari: number
    biaya_idr: number
    ungroupable: number
  } | null
  correction: Correction | null
}

/** Confidence bands for the overlay.
 *
 * Three bands, not a gradient. The engine reports confidence coarsely — in
 * practice a handful of distinct values — so a continuous scale would imply a
 * precision the number does not have. The bands say what a koder needs: read
 * cleanly, read with doubt, or barely read at all. */
export function band(c: number): 'ok' | 'soft' | 'weak' {
  if (c >= 0.9) return 'ok'
  if (c >= 0.45) return 'soft'
  return 'weak'
}

/* The labels as printed on the form. The panel sits beside a photograph of
 * that form with a box drawn on each one, so these must stay word for word
 * what the sheet says — that pairing is the only thing the panel is for. */
export const FIELD_ID: Record<string, string> = {
  cabang: 'Cabang BPJS',
  jenis_penagihan: 'Jenis penagihan',
  jenis_pelayanan: 'Jenis pelayanan',
  nama_pengaju: 'Nama pengaju',
  nama_penderita: 'Nama penderita',
  no_kartu_peserta: 'No. kartu peserta',
  alamat: 'Alamat',
  telpon: 'Telepon',
  nama_ppk: 'Nama PPK',
  kode_ppk: 'Kode PPK',
  bulan_pelayanan: 'Bulan pelayanan',
  peserta: 'Peserta',
}

export const SEVERITY_ID: Record<Severity, { label: string; css: string }> = {
  blocking: { label: 'Ditahan', css: 'sev-block' },
  advisory: { label: 'Perlu dicek', css: 'sev-adv' },
  needs_human_read: { label: 'Baca ulang', css: 'sev-read' },
}

/** Returns null when the export has not been run, so the caller can say so. */
export async function loadIntake(
  url = './data/intake.json',
): Promise<IntakePayload | null> {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    return (await res.json()) as IntakePayload
  } catch {
    return null
  }
}
