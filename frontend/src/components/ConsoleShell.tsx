import type { ReactNode } from 'react'
import { useTickStore } from '../store/useTickStore'

export type GovernmentRoute = 'dashboard' | 'commander' | 'whatif' | 'audit' | 'announce'

const NAV: Array<[GovernmentRoute, string]> = [
  ['dashboard', 'Dashboard'],
  ['commander', 'AI Emergency Commander'],
  ['whatif', 'What-if Simulator'],
  ['audit', 'Audit'],
  ['announce', 'Announce'],
]

/** The Government shell — 5 flat top-level workspaces (SIH26001 master frontend prompt §3),
 * replacing the prior 6-workspace Situation/Impact/Priority/Commander/Audit/Trust nav. The map
 * is NOT a shell-level singleton in this IA (only Dashboard renders MapView) — sub-project 2
 * decides whether that needs to change once the heatmap/layers work lands. */
export function ConsoleShell({
  route,
  onRoute,
  onCitizenNavigate,
  children,
}: {
  route: GovernmentRoute
  onRoute: (route: GovernmentRoute) => void
  onCitizenNavigate: () => void
  children: ReactNode
}) {
  const aoi = useTickStore((s) => s.aoi)
  const modeState = useTickStore((s) => s.modeState)
  const latestTick = useTickStore((s) => s.latestTick)
  const mode = latestTick?.mode ?? modeState?.mode ?? 'live'
  const tick = latestTick?.t ?? modeState?.scenario_time

  return (
    <main className="console-shell">
      <header className="console-topbar">
        <button className="brand" onClick={() => onRoute('dashboard')} aria-label="NIRANTAR Dashboard">
          <span className="brand-mark">N</span>
          <span>
            NIRANTAR
            <small>Decision & Dissemination</small>
          </span>
        </button>
        <span className={`mode-chip ${mode}`}>{mode === 'replay' ? 'REPLAY · RECONSTRUCTED' : 'LIVE'}</span>
        <div className="top-meta">
          <span>AOI</span>
          <strong>{aoi?.name ?? 'Aizawl'}</strong>
        </div>
        <div className="top-meta">
          <span>Current tick</span>
          <strong>{tick ? new Date(tick).toLocaleString() : 'Awaiting feed'}</strong>
        </div>
        <button className="role-switch" type="button" onClick={onCitizenNavigate}>
          Citizen demo ↗
        </button>
      </header>
      <nav className="primary-nav" aria-label="Government workspaces">
        {NAV.map(([key, label]) => (
          <button key={key} className={route === key ? 'active' : ''} onClick={() => onRoute(key)}>
            {label}
          </button>
        ))}
      </nav>
      {children}
      <footer className="provenance">
        MODE: {mode.toUpperCase()}
        <br />
        TICK: {tick ? new Date(tick).toLocaleTimeString() : '—'}
        <br />
        MODEL: {latestTick?.cell_risks[0]?.model_version ?? 'Awaiting model metadata'}
        <br />
        RECONSTRUCTED: {latestTick?.is_reconstructed ? 'YES' : 'NO'}
      </footer>
    </main>
  )
}
