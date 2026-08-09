import { useEffect, useState } from 'react'
import type { Loaded } from './types'
import { load } from './data'
import { AdvisoryBanner, DroppedSpanBanner } from './components/Banners'
import { QueueView } from './components/QueueView'
import { CaseView } from './components/CaseView'
import { StagingTray } from './components/StagingTray'
import { HeroCards } from './components/Hero'

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

export default function App() {
  const [state, setState] = useState<Loaded | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('hero')
  const [openCase, setOpenCase] = useState<string | null>(null)
  const [staged, setStaged] = useState<Set<string>>(new Set())

  useEffect(() => {
    load().then(setState).catch((e) => setError(String(e)))
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
  }

  return (
    <div className="app" data-mode={mode}>
      <header className="floathdr">
        <button className="hpill brandpill" onClick={toHero}>
          <span className="dot" />
          Vitera
        </button>

        <div className="hspacer" />

        {mode === 'work' && (
          <div className="hpill statpill">
            <span className="led" />
            {payload.episodes.length} episode · seed{' '}
            <b className="mono">{payload.generated.seed}</b>
          </div>
        )}

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
        <HeroCards payload={payload} onEnter={() => setMode('work')} />

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
            <AdvisoryBanner payload={payload} />
            <DroppedSpanBanner dropped={droppedFlags} />
            <main>
              {ep ? (
                <CaseView
                  ep={ep}
                  staged={staged}
                  onStage={stage}
                  onDismiss={dismiss}
                  onBack={() => setOpenCase(null)}
                />
              ) : (
                <QueueView episodes={payload.episodes} onOpen={setOpenCase} />
              )}
            </main>
            <footer className="prose">{payload.generated.note}</footer>
          </div>
        </section>
      </div>

      <StagingTray items={[...staged]} onClear={() => setStaged(new Set())} />
    </div>
  )
}
