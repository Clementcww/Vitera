/* Plain-language glossary, inline.
 *
 * The koder knows every one of these words; a judge, an investor or a member
 * of the public does not, and the UI has to hold both audiences without
 * splitting into two apps. So domain terms render with a dotted underline and
 * a one-sentence definition on hover/focus, written in plain language, defining
 * the thing, never marketing it.
 *
 * Native `title` plus a visible affordance, no tooltip library: it works on
 * every device the demo might run on, costs nothing when ignored, and the
 * koder who already knows the words never has to interact with it.
 */

const GLOSSARY: Record<string, string> = {
  bpjs: 'BPJS Kesehatan, Indonesia’s national health insurer. Hospitals bill it for the care they deliver, one claim per admission.',
  klaim:
    'A hospital’s bill to BPJS for one patient’s care. If a document is missing or a code is wrong it comes back unpaid.',
  'klaim-pending':
    'A claim BPJS returned instead of paying. The hospital corrects it and resubmits, and payment slips by weeks.',
  koder:
    'The hospital staff member who turns a doctor’s notes into standard diagnosis codes. The main user of this application.',
  dpjp: 'The attending doctor: the one responsible for the patient and for writing the discharge summary.',
  sep: 'The eligibility letter BPJS issues when a patient is admitted, confirming the admission is covered.',
  cbg: 'An INA-CBG tariff group. Each combination of diagnoses falls into one group with a fixed package price, so a wrong code means a wrong price.',
  grouper:
    'Deterministic software that works out the tariff group from the codes. The only source of rupiah figures here. The AI never produces a monetary figure.',
  'resume-medis':
    'The discharge summary the doctor writes when the patient goes home. The document BPJS reads most closely.',
  cppt: 'The daily progress note, written each day of the admission.',
  'rekam-medis':
    'Everything recorded about the patient’s care: daily notes, laboratory results, medication list, discharge summary.',
  komorbiditas:
    'A condition alongside the main diagnosis, such as diabetes in a pneumonia patient. If it is not written down, BPJS does not pay for it.',
  abstain:
    'The system says it cannot tell, and hands the judgement to a person rather than guessing. That honesty is deliberate, and it is measured.',
  advisory:
    'The mode the system runs in when the AI layer is unavailable: simple rule checks only, and it says so plainly rather than looking complete.',
  'cross-encoder':
    'A small AI model, run inside the hospital rather than in the cloud, that judges one thing only: whether the record supports the code.',
  verbatim:
    'A word-for-word quote from the source document. A finding that cannot quote the record is dropped automatically.',
  fpk: 'The paper cover sheet that accompanies a hospital’s claim file to BPJS, carrying the case count, the total days of care and the amount claimed.',
  ocr: 'Machine reading of text in an image. Used here to read scanned paper forms, and every value it reads carries a confidence.',
  ritl: 'Advanced inpatient care, meaning a stay in a hospital. Distinct from clinic-level care, and only hospital stays are handled in this version.',
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
