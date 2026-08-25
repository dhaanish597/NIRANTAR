import { useTickStore } from '../store/useTickStore'

interface Props {
  open: boolean
  onClose: () => void
}

export function ScenarioPickerModal({ open, onClose }: Props) {
  const scenarios = useTickStore((s) => s.scenarios)
  const startReplay = useTickStore((s) => s.startReplay)

  if (!open) return null

  const handleRun = async (scenarioId: string) => {
    await startReplay(scenarioId)
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg bg-slate-900 p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Run Case Study</h2>
        {scenarios.length === 0 && (
          <p className="text-sm text-slate-400">No scenarios available.</p>
        )}
        <ul className="space-y-3">
          {scenarios.map((scenario) => (
            <li
              key={scenario.id}
              className="flex items-center justify-between rounded border border-white/10 p-3"
            >
              <div>
                <div className="font-medium">{scenario.id}</div>
                <div className="text-xs text-slate-400">
                  {scenario.frame_count} frames · {scenario.aoi_id}
                  {scenario.held_out_of_training ? ' · held out of training' : ''}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void handleRun(scenario.id)}
                className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
              >
                Run
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={onClose}
          className="mt-4 text-sm text-slate-400 hover:text-slate-200"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
