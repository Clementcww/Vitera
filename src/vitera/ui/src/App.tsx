import { useEffect, useState } from 'react'
import type { Loaded } from './types'
import { load } from './data'
import { AdvisoryBanner, DroppedSpanBanner } from './components/Banners'
import { QueueView } from './components/QueueView'
import { CaseView } from './components/CaseView'
import { StagingTray } from './components/StagingTray'
import { SurfaceView } from './three/SurfaceView'
import { Hero } from './components/Hero'

type Tab = 'hero' | 'queue' | 'surface'

export default function App() {
  const [state, setState] = useState<Loaded | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('hero')
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

  const stage = (key: string) =>
    setStaged((s) => new Set(s).add(key))
  const dismiss = (key: string) =>
    setStaged((s) => {
      const n = new Set(s)
      n.delete(key)
      return n
    })

  // The hero is an entry state, not a page: full bleed, no chrome, and it is
  // never returned to once the koder is working.
  if (tab === 'hero') {
    return (
      <Hero
        payload={payload}
        onEnter={() => setTab('queue')}
        onSurface={() => setTab('surface')}
      />
    )
  }

  return (
    <>
      <header>
        <div className="brand">
          <span className="dot" />
          Vitera
        </div>
        <div className="site">Unit Casemix · kohort tersimpan</div>
        <div className="spacer" />
        <nav className="tabs">
          <button
            className={tab === 'queue' ? 'on' : ''}
            onClick={() => {
              setTab('queue')
              setOpenCase(null)
            }}
          >
            Antrean
          </button>
          <button
            className={tab === 'surface' ? 'on' : ''}
            onClick={() => setTab('surface')}
          >
            Permukaan
          </button>
        </nav>
        <div className="pill">
          <span className="led" />
          {payload.episodes.length} episode · seed{' '}
          <b className="mono">{payload.generated.seed}</b>
        </div>
      </header>

      <AdvisoryBanner payload={payload} />
      <DroppedSpanBanner dropped={droppedFlags} />

      <main>
        {tab === 'surface' ? (
          <SurfaceView
            cells={payload.surface.cells}
            maxDay={payload.surface.max_day}
          />
        ) : ep ? (
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

      <StagingTray items={[...staged]} onClear={() => setStaged(new Set())} />

      <footer className="prose">{payload.generated.note}</footer>
    </>
  )
}
