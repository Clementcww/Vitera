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
  /** What the finding is about: an ICD-10 code, an ICD-9-CM procedure, a
   *  doc_id, or a claim field. The queue leads rows with it, because eleven
   *  rows of the same templated sentence are unskimmable and this is the part
   *  that varies. */
  subject: string
  /** Class + subject + evidence hash. The koder's dismissal is keyed on it,
   *  so a dismissal survives a new day and dies on new evidence. */
  suppression_key: string
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
  /** Findings visible for the FIRST time on this day of stay. `flags` is the
   *  standing count and falls as the cohort discharges, which is a denominator
   *  artefact; this is the quantity the concurrent claim is actually about. */
  new: number
  verdict: Verdict
  value_idr: number
  remedy: string | null
  classes: string[]
  codes: Record<string, string>
}

export interface ThresholdProfile {
  flag_at: number
  code_false_positive_rate: number
  recall: number
  precision: number
}

export interface Measured {
  detection_rate: number
  lead_time_median_days: number | null
  lead_time_share_ge_2_days: number | null
  n_episodes: number
  pipeline_runs: number | null
  detection_by_share_of_stay: { share_of_stay: number; detection_rate: number }[]
  lead_time_by_class: Record<string, number | null>
  /** The adoption-critical counterweight to the detection rate. Quoting recall
   *  without it is forbidden by CLAUDE.md and is the first thing a judge asks. */
  clean_fp: {
    /** Binned by SHARE of stay, not by day. A per-day series changes cohort as
     *  it advances — day 13 holds only the episodes that stayed 13 days — so
     *  its slope is partly a change of population. Same reason the detection
     *  curve uses this axis. */
    by_share_of_stay: {
      share_of_stay: number
      clean_fp_rate: number
      n: number
    }[]
    at_discharge: number | null
    at_discharge_by_hospital_class: Record<string, number>
    worst_rate: number | null
    best_rate: number | null
    basis: string
  }
  latency: {
    seconds_per_run_mean?: number
    zero_llm_share?: number
    hardware?: string
    note?: string
  }
  operating_point?: {
    active: string
    profiles: Record<string, ThresholdProfile>
    source: string
  }
  source: string
}

export interface Payload {
  /** Headline metric from the full held-out split; null until measured. */
  measured: Measured | null
  generated: {
    seed: number
    cohort: number
    cohort_caveat: string
    model: string | null
    model_unavailable: string | null
    advisory: boolean
    note: string
  }
  episodes: EpisodeView[]
  surface: { max_day: number; cells: SurfaceCell[] }
}

/* --- the sweep (data/sweep.json, written by `make sweep-demo`) ------------ */

export interface SweepFlagGroup {
  episode_id: string
  sweep_date: string
  day_of_stay: number
  still_admitted: boolean
  previous_successful_sweep: string | null
  recoverable_idr: number
  queue_weight: number
  citation_moved: number
  new: Flag[]
  escalated: Flag[]
  resolved: Flag[]
  documented: Flag[]
}

export interface SweepNight {
  sweep_date: string
  status: 'complete' | 'partial' | 'advisory'
  episodes_run: number
  skipped: { episode_id: string; error: string }[]
  ceiling_hit: string | null
  advisory: boolean
  llm_calls: number
  queue: SweepFlagGroup[]
}

export interface SweepPayload {
  generated: {
    seed: number
    mode: 'replay' | 'night'
    finished_at: string
    llm_mode: string
    note: string
  }
  /** Sweep rule 5. The queue reports THIS, never the last attempted run — a
   *  stale queue rendering as a fresh one is the failure that gets a patient
   *  discharged with an unrepaired record while the screen looks green. */
  last_successful_sweep: string | null
  last_attempted_sweep: string | null
  status: 'complete' | 'partial' | 'advisory' | 'empty'
  metrics: {
    nights: number
    episode_days_run: number
    queue_items: number
    alerts_per_episode_per_day: number
    alerts_ceiling: number
    flag_churn_rate: number
    churn_ceiling: number
    closed_by_documentation: number
    disappeared_unexplained: number
    citations_moved: number
    ceiling_breaches: string[]
    churn_caveat: string
    sweep_wall_clock_seconds: number
    seconds_per_episode_day: number | null
    llm_calls_per_sweep: number
    zero_llm_episode_share: number | null
    cost_per_sweep_idr: number
    cost_basis: string
    statuses: string[]
  }
  nights: SweepNight[]
}

/** Set by the client after re-verifying spans. See data.ts. */
export interface Loaded {
  payload: Payload
  droppedFlags: number
}
