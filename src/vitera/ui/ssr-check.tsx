// Regression check for the white-screen bug: a `measured` block from an older
// export lacks `clean_fp`. That must hide one panel, not kill the app.
import { renderToString } from 'react-dom/server'
import { Dashboard } from './src/components/Dashboard'
import demo from './dist/data/demo.json'
import sweep from './dist/data/sweep.json'

/* eslint-disable @typescript-eslint/no-explicit-any */
const full = demo as any
const degraded = {
  ...full,
  measured: { ...full.measured, clean_fp: undefined, operating_point: undefined },
}
const noMeasured = { ...full, measured: undefined }
const noSweepMetrics = { ...(sweep as any), metrics: undefined }

const cases: [string, any, any][] = [
  ['full payload', full, sweep],
  ['no clean_fp / no operating_point', degraded, sweep],
  ['no measured at all', noMeasured, sweep],
  ['sweep without metrics', full, noSweepMetrics],
]

let failed = 0
for (const [name, p, s] of cases) {
  try {
    const n = renderToString(
      <Dashboard payload={p} sweep={s} variant="surface" />,
    ).length
    console.log(`  ok   ${name} (${n} bytes)`)
  } catch (e) {
    failed++
    console.log(`  FAIL ${name}: ${e instanceof Error ? e.message : e}`)
  }
}
/* commits.ts. The interesting cases are the ones a demo actually hits: a key
   whose parts are missing, and a machine with no localStorage. */
import {
  commitBundle,
  newCommit,
  parseKey,
  readCommits,
  writeCommits,
} from './src/commits'

const check = (name: string, cond: boolean) => {
  if (cond) console.log(`  ok   ${name}`)
  else {
    failed++
    console.log(`  FAIL ${name}`)
  }
}

console.log('\ncommits:')
const k = parseKey('EP000227:D3:abc123:0')
check('parseKey splits a well-formed key', k.episode_id === 'EP000227' && k.defect_class === 'D3' && k.evidence_hash === 'abc123')
const bare = parseKey('EP1')
check('parseKey survives a key with no separators', bare.episode_id === 'EP1' && bare.defect_class === '')

const a = newCommit(['EP1:D3:h:0', 'EP2:D5:h:1'], 20260731, 'Sri')
check('newCommit records every item', a.items.length === 2)
check('newCommit stamps who and which cohort', a.by === 'Sri' && a.seed === 20260731)
check('newCommit ids are unique', newCommit([], 1, 'x').id !== newCommit([], 1, 'x').id)

// No localStorage in node: must degrade, never throw.
check('readCommits returns [] without localStorage', Array.isArray(readCommits()) && readCommits().length === 0)
let threw = false
try {
  writeCommits([a])
} catch {
  threw = true
}
check('writeCommits does not throw without localStorage', !threw)

const bundle = commitBundle([a])
check('exported bundle is marked DRAF', bundle.status === 'DRAF')
check('exported bundle carries its own disclaimer', /tidak dikirim ke BPJS/i.test(bundle.disclaimer))

/* Hook order in App.tsx.
 *
 * App has two early returns (`error`, and `!state` while loading). A hook
 * declared below them runs on some renders and not others: React error #310,
 * which shows up as a blank page and nothing else. tsc does not catch it and
 * there is no eslint here, so this is the guard -- a line-number comparison,
 * which is all the rule actually is. */
import { readFileSync } from 'node:fs'

console.log('\nhook order:')
const src = readFileSync('src/App.tsx', 'utf8').split('\n')
const hookAt: number[] = []
let firstGuard = -1
src.forEach((line, i) => {
  if (/^\s+const \[.*\] = useState|^\s+use(Effect|Memo|Ref|Callback)\(/.test(line))
    hookAt.push(i + 1)
  // A top-level `if (` inside the component body: the start of an early return.
  if (firstGuard < 0 && /^ {2}if \(/.test(line)) firstGuard = i + 1
})
const lastHook = Math.max(...hookAt)
check(
  `every hook (${hookAt.length}) is declared before the first early return`,
  firstGuard > 0 && lastHook < firstGuard,
)
if (firstGuard > 0 && lastHook >= firstGuard)
  console.log(`       hook on line ${lastHook} is below the guard on line ${firstGuard}`)

console.log(failed ? `\n${failed} check(s) failed` : '\nall checks pass')
process.exit(failed ? 1 : 0)
