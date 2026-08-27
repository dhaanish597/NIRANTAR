import { useEffect, useState } from 'react'
import { AnnounceWorkspace } from './components/AnnounceWorkspace'
import { AuditTrailView } from './components/AuditTrailView'
import { AuditWorkspace } from './components/AuditWorkspace'
import { CitizenApp, type CitizenRoute } from './components/CitizenApp'
import { CommanderWorkspace } from './components/CommanderWorkspace'
import { ConsoleShell, type GovernmentRoute } from './components/ConsoleShell'
import { CounterfactualScorecard } from './components/CounterfactualScorecard'
import { DashboardWorkspace } from './components/DashboardWorkspace'
import { InstallPrompt } from './components/InstallPrompt'
import { OnboardingOverlay } from './components/OnboardingOverlay'
import { VillageDetailDrawer } from './components/VillageDetailDrawer'
import { WhatIfWorkspace } from './components/WhatIfWorkspace'
import { attachAckQueueAutoSync, syncQueuedAcknowledgements } from './lib/ackQueue'
import { useTickStore } from './store/useTickStore'

const AOI_ID = 'aizawl'

const GOVERNMENT_ROUTES: GovernmentRoute[] = ['dashboard', 'commander', 'whatif', 'audit', 'announce']
const CITIZEN_ROUTES: CitizenRoute[] = ['alert', 'route', 'announcement', 'report']

type Route = `/console/${GovernmentRoute}` | `/citizen/${CitizenRoute}`

function routeFromPath(path: string): Route {
  const citizenMatch = CITIZEN_ROUTES.find((r) => path.startsWith(`/citizen/${r}`))
  if (citizenMatch) return `/citizen/${citizenMatch}`
  const govMatch = GOVERNMENT_ROUTES.find((r) => path.startsWith(`/console/${r}`))
  return govMatch ? `/console/${govMatch}` : '/console/dashboard'
}

function App() {
  const [route, setRoute] = useState<Route>(() => routeFromPath(location.pathname))
  const loadInitial = useTickStore((s) => s.loadInitial)
  const connect = useTickStore((s) => s.connect)
  const disconnect = useTickStore((s) => s.disconnect)
  const hydrate = useTickStore((s) => s.hydrateFromOfflineCache)
  const hydrateCitizenReports = useTickStore((s) => s.hydrateCitizenReports)

  useEffect(() => {
    void hydrate()
    hydrateCitizenReports()
    void loadInitial(AOI_ID)
    connect()
    attachAckQueueAutoSync()
    void syncQueuedAcknowledgements()
    return () => disconnect()
  }, [hydrate, hydrateCitizenReports, loadInitial, connect, disconnect])

  useEffect(() => {
    const onPop = () => setRoute(routeFromPath(location.pathname))
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])

  const navigate = (next: Route) => {
    if (location.pathname !== next) history.pushState({}, '', next)
    setRoute(next)
    window.scrollTo(0, 0)
  }

  if (route.startsWith('/citizen/')) {
    const citizenRoute = route.replace('/citizen/', '') as CitizenRoute
    return (
      <>
        <CitizenApp route={citizenRoute} onNavigate={(r) => navigate(`/citizen/${r}`)} />
        <OnboardingOverlay />
        <InstallPrompt />
      </>
    )
  }

  const govRoute = route.replace('/console/', '') as GovernmentRoute
  return (
    <>
      <ConsoleShell route={govRoute} onRoute={(r) => navigate(`/console/${r}`)}>
        {govRoute === 'dashboard' && <DashboardWorkspace />}
        {govRoute === 'commander' && (
          <CommanderWorkspace
            onAnnounce={() => navigate('/console/announce')}
            onWhatIf={() => navigate('/console/whatif')}
          />
        )}
        {govRoute === 'whatif' && <WhatIfWorkspace />}
        {govRoute === 'audit' && <AuditWorkspace />}
        {govRoute === 'announce' && <AnnounceWorkspace />}
      </ConsoleShell>
      <VillageDetailDrawer />
      <AuditTrailView />
      <CounterfactualScorecard />
      <OnboardingOverlay />
      <InstallPrompt />
    </>
  )
}

export default App
