import { useEffect, useState } from 'react'
import type { Loaded, SweepPayload } from './types'
import type { SeedManifest } from './types'
import { load, loadSeeds, loadSweep } from './data'
import { DemoControls } from './components/DemoControls'
import {
  AdvisoryBanner,
  DroppedSpanBanner,
  SweepStatus,
  StaleBanner,
} from './components/Banners'
import { QueueView } from './components/QueueView'
import { Logo } from './components/Logo'
import { CaseView } from './components/CaseView'
import { StagingTray } from './components/StagingTray'
import { CommitLog } from './components/CommitLog'
import type { CommitEntry } from './commits'
import { newCommit, readCommits, writeCommits } from './commits'
import { HeroCards } from './components/Hero'
import { About } from './components/About'
import { HeroKey, KeyPanel } from './components/KeyPanel'
import { ScanView } from './components/ScanView'
import { ReportSheet } from './components/ReportSheet'
import { keyStore } from './llm'
import type { IntakePayload } from './intake'
import { loadIntake } from './intake'

/* One page.
 *
 * There are no routes and no tabs. The landing and the workbench are the same
 * DOM, and the dark bento card is the hinge between them: in `hero` mode it is
 * a card summarising the morning queue, and in `work` mode that same element
 * has grown to fill the frame, shed its radius, turned from ink to canvas, and
 * is now holding the queue itself.
 *
 * That is a morph rather than a navigation, and it is worth the small amount of
 * state it costs. The koder sees the thing they clicked become the thing they
 * asked for, so the summary and the detail are visibly the same object. A
 * route change would have thrown one screen away and drawn another.
 *
 * The card keeps its own scroll in `work` mode rather than growing the page,
 * because a container whose geometry is being transitioned cannot also be in
 * normal flow: `top/left/width/height` animate, `position: static` does not.
 */

type Mode = 'hero' | 'work'

/* Which pane the workbench is showing.
 *
 * `queue` is the koder's day; `scan` is the paper the batch arrived on. They
 * are panes rather than routes for the same reason the landing is: the card
 * that morphed into the workbench stays the same element, and a route change
 * would throw it away.
 *
 * The unit summary is deliberately NOT a third pane. It answers a different
 * question, for a different person (is the unit on top of this month) and it
 * reads against the day-of-stay surface rather than against the queue. It
 * lives in the accent card on the landing, where that surface already is. */
type Pane = 'queue' | 'scan'

export default function App() {
  const [state, setState] = useState<Loaded | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('hero')
  const [pane, setPane] = useState<Pane>('queue')
  const [openCase, setOpenCase] = useState<string | null>(null)
  const [staged, setStaged] = useState<Set<string>>(new Set())
  const [keyTick, setKeyTick] = useState(0)
  const [intake, setIntake] = useState<IntakePayload | null>(null)
  const [sweep, setSweep] = useState<SweepPayload | null>(null)
  const [report, setReport] = useState(false)
  // Which landing card is currently expanded over the bento. Both cover the
  // headline card, which is why the 3D layer reads them: see Hero.tsx.
  const [surface, setSurface] = useState(false)
  const [about, setAbout] = useState(false)

  /* The demo controls above the queue. `swept` is the queue's own state, not
     the sweep's: the payload is loaded either way, and this decides whether
     the workbench has been shown it yet. Pressing the button once per cohort
     is the whole interaction; switching cohort puts it back. */
  const [seeds, setSeeds] = useState<SeedManifest | null>(null)
  const [seed, setSeed] = useState<number | null>(null)
  const [swept, setSwept] = useState(false)
  const [busy, setBusy] = useState(false)
  /* Rule 1's record: read once at mount so a reload does not lose what a human
     accepted, written on every commit. See commits.ts for why this is a draft
     log and not a claim write.

     It belongs UP HERE with the other hooks, not down beside the `commit`
     handler where it reads better. Two early returns sit between the two
     places (`error`, and `!state` while loading), so a hook declared below
     them runs on some renders and not others, which is React error #310 and a
     white screen. Handlers may live anywhere; hooks may not. */
  const [commits, setCommits] = useState<CommitEntry[]>(readCommits)

  useEffect(() => {
    load().then(setState).catch((e) => setError(String(e)))
    // Optional, and deliberately not awaited with the main payload: a missing
    // intake export costs one tab, never the workbench.
    loadIntake().then(setIntake)
    // Same, and with one extra rule: absent sweep output means the header says
    // no sweep has run. It must never fall back to a timestamp of its own.
    loadSweep().then(setSweep)
    // Same again: no manifest means no seed control, on the canonical cohort.
    loadSeeds().then(setSeeds)
  }, [])

  if (error) {
    return (
      <div className="fatal">
        <h1>Data tidak dapat dimuat</h1>
        <p className="prose">{error}</p>
        <pre>make ui-data</pre>
      </div>
    )
  }
  if (!state) return <div className="loading">memuat…</div>

  const { payload, droppedFlags } = state
  const ep = payload.episodes.find((e) => e.episode_id === openCase) ?? null

  /* What the WORKBENCH has been shown. Until the sweep is run, the header
     reads `belum ada sweep` and the queue carries no diff marks, which is the
     state the app already had to handle for a missing export (sweep rule 5)
     rather than a new one invented for the demo.
     The landing keeps the full payload: the dashboard there reports a sweep
     that DID run, in the past tense, and says which night it was. */
  const queueSweep = swept ? sweep : null
  const activeSeed = seed ?? seeds?.default ?? payload.generated.seed

  const commit = (by: string) => {
    const entry = newCommit([...staged], activeSeed, by)
    const next = [entry, ...commits]
    setCommits(next)
    writeCommits(next)
    setStaged(new Set())
  }
  const resetCommits = () => {
    setCommits([])
    writeCommits([])
  }

  const stage = (key: string) => setStaged((s) => new Set(s).add(key))
  const dismiss = (key: string) =>
    setStaged((s) => {
      const n = new Set(s)
      n.delete(key)
      return n
    })

  /* Switching cohort reloads both files and resets the queue to un-swept.
   *
   * Everything derived from the old cohort goes with it: an open case and a
   * staged correction both name episodes that no longer exist in the payload,
   * and carrying them across would leave the staging tray holding keys against
   * a ward that is not on screen. */
  const chooseSeed = async (next: number) => {
    const entry = seeds?.seeds.find((s) => s.seed === next)
    if (!entry || busy) return
    setBusy(true)
    try {
      const loaded = await load(`./data/${entry.demo}`)
      const sw = await loadSweep(`./data/${entry.sweep}`)
      setState(loaded)
      setSweep(sw)
      setSeed(next)
      setSwept(false)
      setOpenCase(null)
      setStaged(new Set())
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const toHero = () => {
    setMode('hero')
    setOpenCase(null)
    setReport(false)
  }

  /* The dark card is the workbench in `work` mode and About Vitera on the
     landing. Entering the workbench while About is expanded would hand the
     morph two geometries at once, so the expansion is closed first. */
  const toWork = () => {
    setAbout(false)
    setMode('work')
  }

  return (
    <div className="app" data-mode={mode}>
      <header className="floathdr">
        <button className="hpill brandpill" onClick={toHero}>
          <Logo size={17} />
          Vitera
        </button>

        <div className="hspacer" />

        {/* On the landing the pill IS the key field, and it stands where the
            call to action used to: the only thing a judge has to bring is the
            one thing the header asks for. In the workbench it collapses back
            to the toggle, because there the screen is the koder's, not a
            visitor's. Same store, same copy, one component apart. */}
        {mode === 'hero' ? (
          <HeroKey onChange={() => setKeyTick((n) => n + 1)} />
        ) : (
          <KeyPanel
            hasKey={Boolean(keyStore.get()) || keyTick < 0}
            onChange={() => setKeyTick((n) => n + 1)}
          />
        )}

        {mode === 'work' && (
          <div className="hpill panepill">
            <button
              className={pane === 'queue' ? 'on' : ''}
              onClick={() => setPane('queue')}
            >
              Antrean
            </button>
            {intake && (
              <button
                className={pane === 'scan' ? 'on' : ''}
                onClick={() => {
                  setPane('scan')
                  setOpenCase(null)
                }}
              >
                Berkas pindaian
              </button>
            )}
          </div>
        )}

        {/* The header's job here is to say WHEN, not what seed. A queue with
            no clock on it renders as fresh no matter how old it is, which is
            the sweep-rule-5 failure that gets a patient discharged with an
            unrepaired record while the screen looks green. */}
        {mode === 'work' && <SweepStatus sweep={queueSweep} payload={payload} />}

        {/* No door in the header on the landing: the key field took this slot,
            and the way in is the accent card's button. Only the way back
            remains, and only once there is somewhere to come back from. */}
        {mode === 'work' && (
          <button className="hpill ctapill" onClick={toHero}>
            <span aria-hidden="true">←</span> Beranda
          </button>
        )}
      </header>

      <div className={'bento' + (about ? ' aboutopen' : '')}>
        <HeroCards
          payload={payload}
          sweep={sweep}
          onEnter={toWork}
          onSurface={setSurface}
          paused={mode === 'work' || surface || about}
        />

        {/* The hinge. Card in `hero`, whole workbench in `work`.
         *
         * It is still the element that morphs, but it is no longer the thing
         * you click to make that happen: on the landing it is About Vitera,
         * and the door is the accent card's button. Two cards that both opened
         * the queue meant the landing had to explain which one to press. */}
        <section className={'card card-work' + (about ? ' expanded' : '')}>
          <About expanded={about} onExpand={setAbout} />

          <div className="workpane">
            <StaleBanner sweep={queueSweep} />
            <AdvisoryBanner payload={payload} />
            <DroppedSpanBanner dropped={droppedFlags} />
            <main>
              {pane === 'scan' && intake ? (
                <ScanView data={intake} onReport={() => setReport(true)} />
              ) : ep ? (
                <CaseView
                  ep={ep}
                  staged={staged}
                  onStage={stage}
                  onDismiss={dismiss}
                  onBack={() => setOpenCase(null)}
                />
              ) : (
                <QueueView
                  /* A new cohort is a new screen, so the queue remounts rather
                     than inheriting the last one's state. Without this the
                     filter chosen for the previous ward survives the switch,
                     and a cohort of 36 can land showing three rows because a
                     remedy filter from a different ward is still applied. */
                  key={activeSeed}
                  episodes={payload.episodes}
                  sweep={queueSweep}
                  onOpen={setOpenCase}
                  grouped={swept}
                  controls={
                    <DemoControls
                      manifest={seeds}
                      seed={activeSeed}
                      onSeed={chooseSeed}
                      swept={swept}
                      onSweep={() => setSwept(true)}
                      sweep={sweep}
                      busy={busy}
                    />
                  }
                />
              )}
            </main>
            {/* `generated.note` says this in English, for the paper and for
                `results/`. It is not what a koder should be made to read, for
                the same reason the churn caveat is restated in Dashboard.tsx:
                a raw English string on this screen is a leak, not a citation.
                Same three guarantees, in the reader's language, no rule
                numbers. The note itself stays in the payload. */}
            <CommitLog entries={commits} onReset={resetCommits} />
            {/* Three separate guarantees read as one grey paragraph and got
                skipped. They are three, so they are set as three. */}
            <footer className="guarantees">
              <span>Semua angka di layar ini keluaran pipeline.</span>
              <span>Rupiah dihitung grouper, tidak pernah oleh model AI.</span>
              <span>Kutipan dicocokkan ulang ke dokumen aslinya; yang tidak cocok dibuang.</span>
            </footer>
          </div>
        </section>
      </div>

      <StagingTray
        items={[...staged]}
        onClear={() => setStaged(new Set())}
        onCommit={commit}
      />

      {report && intake && (
        <ReportSheet data={intake} onClose={() => setReport(false)} />
      )}
    </div>
  )
}
