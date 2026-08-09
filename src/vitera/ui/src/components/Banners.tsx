import type { Payload } from '../types'

/* Two banners, both of which exist because of a rule that is easy to satisfy
 * badly.
 *
 * Advisory (rule 8): the system must remain useful with the model layer off.
 * The failure mode is not that it stops working — it is that a rules-only run
 * renders identically to a full one and the koder trusts a check that never
 * happened. So the banner names the classes that were NOT examined. "Degraded
 * mode" tells a koder nothing; "D2, D3, D4 and D7 were not checked tonight"
 * tells them exactly which claims still need a human.
 *
 * Staleness (sweep rule 5): a stale queue must never render as a fresh one.
 * The header shows the last SUCCESSFUL run, not the last attempted one. */

export function AdvisoryBanner({ payload }: { payload: Payload }) {
  const ep = payload.episodes.find((e) => e.advisory)
  if (!payload.generated.advisory && !ep) return null
  const unchecked = ep?.classes_unchecked ?? ['D2', 'D3', 'D4', 'D5', 'D7']

  return (
    <details className="banner b-adv" open>
      <summary>
        <span className="mark">~</span>
        Advisory mode: deterministic rules only
        <span className="more">details</span>
      </summary>
      <div className="detail">
        The model layer was unavailable and the pipeline ran without it. Classes{' '}
        <b>{unchecked.join(', ')} went unchecked</b> on this run. A clean queue does not mean a clean claim.
        {payload.generated.model_unavailable && (
          <div className="why-mono">{payload.generated.model_unavailable}</div>
        )}
      </div>
    </details>
  )
}

export function DroppedSpanBanner({ dropped }: { dropped: number }) {
  if (!dropped) return null
  return (
    <details className="banner b-stale">
      <summary>
        <span className="mark">!</span>
        {dropped} findings dropped: the quote did not match the record
        <span className="more">details</span>
      </summary>
      <div className="detail">
        Every finding must point at a verbatim quote in the document it cites
        (aturan arsitektur 6). Pemeriksaan diulang di sisi klien terhadap teks
        before it is shown. Anything that cannot is dropped rather than shown
        with the quote loosened until it fits.
      </div>
    </details>
  )
}
