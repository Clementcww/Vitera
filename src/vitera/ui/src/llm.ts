/* The browser side of the model boundary.
 *
 * The workbench is a static bundle with no server of its own, so when a judge
 * supplies their own key the call goes from their browser straight to the
 * provider. That places two of the architectural rules in this file, and they
 * are the reason it exists rather than a fetch inlined in a component.
 *
 * rule 3  the LLM never sees re-identified data. `pseudonymise` is a port of
 *         the patterns in `agent/boundary.py`, and `explain` refuses to send
 *         anything that did not come out of it. Over-redaction costs the model
 *         a little context; under-redaction is a UU 27/2022 problem. The demo
 *         corpus is synthetic, so nothing here is a real patient, but the
 *         boundary has to be real or it is not a boundary.
 *
 * rule 2  no clinical determination originates from the LLM. What is sent is a
 *         finding that already exists, with its class, remedy, score and
 *         citation fixed, and what comes back is one sentence of prose. The UI
 *         renders that beside the deterministic rationale rather than instead
 *         of it, so a judge can see which layer said what.
 *
 * The key is never persisted to disk and never sent anywhere except the
 * provider endpoint. It lives in sessionStorage, which dies with the tab.
 */

const PATTERNS: [RegExp, string][] = [
  [/\bNIK[:\s]*\d{16}\b/g, '[NIK]'],
  [/\b\d{16}\b/g, '[NIK]'],
  [/\bSEP\d+\b/g, '[SEP]'],
  [/\bNo\.\s*RM[:\s]*\d+\b/g, '[NO_RM]'],
  [/\b\d{4}-\d{2}-\d{2}\b/g, '[TANGGAL]'],
  [/\b(?:\+62|0)8\d{8,11}\b/g, '[TELEPON]'],
  [/\b(?:Tn|Ny|Nn|An)\.\s*[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*/g, '[NAMA]'],
  [/\bdr\.\s*[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*/g, '[DPJP]'],
]

/** The only route to text that may be sent to a provider. */
export function pseudonymise(text: string): string {
  let out = text
  for (const [re, token] of PATTERNS) out = out.replace(re, token)
  return out
}

/** Belt and braces, mirroring `_looks_reidentified` on the Python side. */
function looksReidentified(text: string): string | null {
  for (const [re, token] of PATTERNS) {
    if (token === '[TANGGAL]') continue // dates survive redaction legitimately
    const m = text.match(re)
    if (m) return m[0]
  }
  return null
}

const KEY_STORE = 'vitera.provider_key'
const MODEL_STORE = 'vitera.provider_model'
export const DEFAULT_MODEL = 'gpt-4o-mini'

export const keyStore = {
  get: () => sessionStorage.getItem(KEY_STORE) ?? '',
  set: (v: string) => sessionStorage.setItem(KEY_STORE, v),
  clear: () => sessionStorage.removeItem(KEY_STORE),
  model: () => sessionStorage.getItem(MODEL_STORE) || DEFAULT_MODEL,
  setModel: (v: string) => sessionStorage.setItem(MODEL_STORE, v || DEFAULT_MODEL),
}

const SYSTEM =
  'You write one sentence of plain English for a medical coder in an ' +
  'Indonesian hospital. The finding has already been settled by a ' +
  'deterministic system; your only job is to explain it clearly. Do not add a ' +
  'new finding, do not change the conclusion, do not mention any figure you ' +
  'were not given, and never tell a doctor what to write. Answer in at most ' +
  'one sentence, with no preamble.'

export class ReidentifiedTextError extends Error {}

export async function explain(
  args: { defect: string; rationale: string; quote: string },
  opts: { key: string; model?: string; signal?: AbortSignal } ,
): Promise<string> {
  const prompt = pseudonymise(
    `In one sentence, for a medical coder, explain why the following finding ` +
      `needs acting on.\nFinding: ${args.defect}\n` +
      `Quote from the record: ${args.quote}\nSystem note: ${args.rationale}`,
  )

  const leaked = looksReidentified(prompt)
  if (leaked) {
    // Refuse rather than redact harder and hope. A boundary that lets one
    // through under pressure was never a boundary.
    throw new ReidentifiedTextError(
      `menolak mengirim teks ter-identifikasi ke model: ${leaked}`,
    )
  }

  let res: Response
  try {
    res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      signal: opts.signal,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${opts.key}`,
      },
      body: JSON.stringify({
        model: opts.model || DEFAULT_MODEL,
        temperature: 0,
        max_completion_tokens: 120,
        messages: [
          { role: 'system', content: SYSTEM },
          { role: 'user', content: prompt },
        ],
      }),
    })
  } catch {
    // A thrown fetch is a transport failure, not an API error, and the bare
    // "Failed to fetch" tells a judge nothing. The causes worth naming are the
    // ones they can act on.
    throw new Error(
      'The request never reached the provider. Check the connection, or ' +
        'anything blocking requests in the browser: an extension, a corporate ' +
        'policy, or a sandboxed browser withholding the credential header.',
    )
  }

  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body.slice(0, 180)}` : ''}`)
  }
  const data = await res.json()
  return (data?.choices?.[0]?.message?.content ?? '').trim()
}
