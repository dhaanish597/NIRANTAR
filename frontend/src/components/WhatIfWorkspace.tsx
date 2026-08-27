import { WhatIfSimulator } from './WhatIfSimulator'

/** The Government "What-if Simulator" top-level workspace (new 5-item IA — previously nested
 * under a "Commander" sub-nav that no longer exists). Thin wrapper: WhatIfSimulator itself is
 * already real (BUILD_PLAN.md task 5.8) and untouched by this sub-project; sub-project 7
 * reorganizes its parameters and gives it a dedicated predictive map. */
export function WhatIfWorkspace() {
  return <WhatIfSimulator />
}
