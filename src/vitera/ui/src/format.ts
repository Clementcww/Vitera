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
    label: 'Ask the doctor',
    who: 'Doctor, needs the patient still on the ward',
    css: 'query',
  },
  OBTAIN: {
    label: 'Attach a document',
    who: 'Records officer, still possible after discharge',
    css: 'obtain',
  },
  RECODE: {
    label: 'Change the code',
    who: 'Coder, still possible until the claim is sent',
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
  D1: 'The claim file is incomplete',
  D2: 'A more specific code exists for what the record describes',
  D3: 'Nothing in the record supports this diagnosis',
  D4: 'A comorbidity is treated in the notes but never coded',
  D5: 'A supporting result was ordered and never attached',
  D6: 'The procedure does not follow from the diagnosis',
  D7: 'Comorbidities added without evidence in the record',
  D8: 'Administrative mismatch in SEP, identity or dates',
}

export const VERDICT: Record<string, string> = {
  clean: 'Nothing found',
  flagged: 'Needs work',
  abstain: 'Needs a coder to judge',
}

export const SOURCE: Record<string, string> = {
  rules: 'rules',
  cross_encoder: 'cross-encoder',
  router: 'router',
}
