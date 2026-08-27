import { WhatIfSimulator } from './WhatIfSimulator'

/** The Government "What-if Simulator" top-level workspace (new 5-item IA — previously nested
 * under a "Commander" sub-nav that no longer exists). Thin wrapper: WhatIfSimulator itself is
 * already real (BUILD_PLAN.md task 5.8) and untouched by this sub-project; sub-project 7
 * reorganizes its parameters and gives it a dedicated predictive map. */
export function WhatIfWorkspace() {
  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">
      <h1 className="mb-1 text-xl font-bold">What-if Simulator</h1>
      <p className="mb-4 text-sm text-slate-400">
        DDMA pre-positioning support — re-runs the real risk/impact/decision pipeline on
        hypothetical rainfall. Results never touch live map state or the audit trail.
      </p>
      <WhatIfSimulator />
    </div>
  )
}
