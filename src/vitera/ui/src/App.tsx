import { useEffect, useState } from 'react'
import type { Loaded, SweepPayload } from './types'
import { load, loadSweep } from './data'
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
import { HeroCards } from './components/Hero'
import { KeyPanel } from './components/KeyPanel'
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

  useEffect(() => {
    load().then(setState).catch((e) => setError(String(e)))
    // Optional, and deliberately not awaited with the main payload: a missing
    // intake export costs one tab, never the workbench.
    loadIntake().then(setIntake)
    // Same, and with one extra rule: absent sweep output means the header says
    // no sweep has run. It must never fall back to a timestamp of its own.
    loadSweep().then(setSweep)
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

  const stage = (key: string) => setStaged((s) => new Set(s).add(key))
  const dismiss = (key: string) =>
    setStaged((s) => {
      const n = new Set(s)
      n.delete(key)
      return n
    })

  const toHero = () => {
    setMode('hero')
    setOpenCase(null)
    setReport(false)
  }

  return (
    <div className="app" data-mode={mode}>
      <header className="floathdr">
        <button className="hpill brandpill" onClick={toHero}>
          <Logo size={17} />
          Vitera
        </button>

        <div className="hspacer" />

        {mode === 'work' && (
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
        {mode === 'work' && <SweepStatus sweep={sweep} payload={payload} />}

        <button
          className="hpill ctapill"
          onClick={() => (mode === 'hero' ? setMode('work') : toHero())}
        >
          {mode === 'hero' ? (
            <>
              Buka antrean <span aria-hidden="true">→</span>
            </>
          ) : (
            <>
              <span aria-hidden="true">←</span> Beranda
            </>
          )}
        </button>
      </header>

      <div className="bento">
        <HeroCards
          payload={payload}
          sweep={sweep}
          onEnter={() => setMode('work')}
        />

        {/* The hinge. Card in `hero`, whole workbench in `work`. */}
        <section
          className="card card-work"
          onClick={() => mode === 'hero' && setMode('work')}
        >
          <div className="teaser">
            <h2>
              Antrean
              <br />
              pagi
            </h2>
            <div className="rings" aria-hidden="true">
              <i />
              <i />
              <i />
            </div>
            <div className="remedies">
              <span className="rdot" style={{ background: 'var(--query)' }} />
              <span className="rdot" style={{ background: 'var(--obtain)' }} />
              <span className="rdot" style={{ background: 'var(--recode)' }} />
              <span className="chip outline">
                {payload.episodes.reduce((n, e) => n + e.flags.length, 0)} temuan
              </span>
            </div>
          </div>

          <div className="workpane">
            <StaleBanner sweep={sweep} />
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
                  episodes={payload.episodes}
                  sweep={sweep}
                  onOpen={setOpenCase}
                />
              )}
            </main>
            <footer className="prose">{payload.generated.note}</footer>
          </div>
        </section>
      </div>

      <StagingTray items={[...staged]} onClear={() => setStaged(new Set())} />

      {report && intake && (
        <ReportSheet data={intake} onClose={() => setReport(false)} />
      )}
    </div>
  )
}
