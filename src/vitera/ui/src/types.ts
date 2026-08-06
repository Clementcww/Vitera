/* Mirrors src/vitera/api/export.py. Nothing here is optional for convenience —
 * a field the exporter always writes is required here, so a schema drift is a
 * type error rather than a blank cell on the demo screen. */

export type Remedy = 'QUERY' | 'OBTAIN' | 'RECODE'
export type Verdict = 'clean' | 'flagged' | 'abstain'
export type FlagSource = 'rules' | 'cross_encoder' | 'router'

export interface Span {
  doc_id: string
  start: number
  end: number
  text: string
  evidence_hash: string
}

export interface Flag {
  defect_class: string
  defect_label: string
  remedy: Remedy
  actor: string
  decay_rank: number
  score: number
  source: FlagSource
  rationale: string
  span: Span
}

export interface Doc {
  doc_id: string
  day: number
  absent: boolean
  text: string
}

export interface Group {
  cbg_code: string | null
  severity: number | null
  tariff_idr: number | null
  ungroupable_reason: string | null
}

export interface Money {
  now: Group
  if_confirmed: Group
  delta_idr: number | null
  source: 'grouper'
}

export interface Trace {
  llm_calls: number
  budget_breach: string | null
  elapsed_seconds: number
  tool_calls: { tool: string; result_digest: string; elapsed_seconds: number }[]
}

export interface EpisodeView {
  episode_id: string
  site_id: string
  day: number
  los_so_far: number
  discharge_day: number | null
  still_admitted: boolean
  admission_date: string
  verdict: Verdict
  verdict_reason: string
  advisory: boolean
  classes_checked: string[]
  classes_unchecked: string[]
  money: Money
  flags: Flag[]
  documents: Doc[]
  validation_failures: { check: string; detail: string }[]
  trace: Trace
}

export interface SurfaceCell {
  e: number
  episode_id: string
  d: number
  flags: number
  verdict: Verdict
  value_idr: number
  remedy: string | null
  classes: string[]
  codes: Record<string, string>
}

export interface Payload {
  generated: {
    seed: number
    cohort: number
    model: string | null
    model_unavailable: string | null
    advisory: boolean
    note: string
  }
  episodes: EpisodeView[]
  surface: { max_day: number; cells: SurfaceCell[] }
}

/** Set by the client after re-verifying spans. See data.ts. */
export interface Loaded {
  payload: Payload
  droppedFlags: number
}
