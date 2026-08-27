import { useTickStore } from '../store/useTickStore'
import { NotBuilt } from './NotBuilt'

/** The Government "Audit" top-level workspace. A page-level list of alert_ids (real, from
 * `useTickStore.auditEvents`) that opens the existing, real, already-tested `AuditTrailView`
 * modal (App.tsx-mounted, Task 14) for the full hash-chained timeline — reused, not rebuilt. */
export function AuditWorkspace() {
  const events = useTickStore((s) => s.auditEvents)
  const openAuditTrail = useTickStore((s) => s.openAuditTrail)
  const alertIds = Array.from(new Set(events.map((e) => e.alert_id)))

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">
      <h1 className="mb-1 text-xl font-bold">Audit</h1>
      <p className="mb-4 text-sm text-slate-400">
        AI Flagged → DDMA Approved → Disseminated → Village Acknowledged
      </p>
      {alertIds.length === 0 ? (
        <NotBuilt
          task="TASK-AUDIT-FEED"
          what="No audit events have been received yet."
          blocks="A live or replay tick"
        />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="pb-2">Alert</th>
              <th className="pb-2">Latest event</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {alertIds.map((alertId) => {
              const latest = events.find((e) => e.alert_id === alertId)
              return (
                <tr key={alertId} className="border-t border-white/10">
                  <td className="py-2 font-mono text-xs">{alertId}</td>
                  <td className="py-2">{latest?.kind}</td>
                  <td className="py-2 text-right">
                    <button
                      type="button"
                      onClick={() => openAuditTrail(alertId)}
                      className="rounded bg-white/10 px-2 py-1 text-xs font-semibold hover:bg-white/20"
                    >
                      View trail
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
