/**
 * Parses the real, committed `data/models/eval_report.md` (BUILD_PLAN.md task 1.16) into typed
 * numbers for the false-alarm-cost slider (task 5.6).
 *
 * `eval_report.md` is a hand-authored Markdown document, not structured JSON — BUILD_PLAN.md's
 * task 5.6 explicitly leaves the choice of how to consume it up to the implementer: parse the
 * specific numbers out of it at build/load time (documented as coupled to the file's current
 * structure, with a test asserting the parse succeeds against the real committed file), or note
 * that the report should eventually also emit a JSON sidecar. This module takes the first option.
 *
 * RULING (documented, not silently decided): a small typed parser reading the two tables in
 * section 5 ("Confusion matrix at three operating thresholds") and section 6 ("False-alarm-cost
 * table") by heading text + Markdown table syntax. This is **tightly coupled to the report's
 * current heading text and column order** — if `ml/evaluate.py` (the script that generates the
 * report) ever changes either, this parser must change with it. It fails loudly (throws a
 * descriptive error) rather than silently returning wrong numbers if a heading or column it
 * expects is missing, and `evalReport.test.ts` asserts the parse succeeds against the real file
 * committed on `main` today. A JSON sidecar emitted by `ml/evaluate.py` alongside the Markdown
 * would remove this coupling entirely — recorded as a followup for whoever next touches
 * `ml/evaluate.py`, not attempted here (this agent may not touch backend/ml files).
 *
 * Read via Vite's `import.meta.glob` with the `?raw` query (bundled at build time, no network
 * round trip) — the same "read the committed file directly" pattern `lib/scenarioDetails.ts`
 * already uses for scenario JSON, consistent with CLAUDE.md rule 10 (the demo runs with the
 * network cable unplugged).
 */

const evalReportModules = import.meta.glob('../../../data/models/eval_report.md', {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>

export interface ConfusionMatrixRow {
  threshold: number
  tp: number
  fp: number
  fn: number
  tn: number
}

export interface FalseAlarmCostRow {
  threshold: number
  cellsFlagged: number
  pctCellsFlagged: number
  eventsCaught: number
  eventsTotal: number
  eventsMissed: number
}

/** One threshold's worth of both tables merged, keyed by the threshold value they share. This is
 * what the slider actually renders per position. */
export interface FalseAlarmOperatingPoint {
  threshold: number
  tp: number
  fp: number
  fn: number
  tn: number
  cellsFlagged: number
  pctCellsFlagged: number
  eventsCaught: number
  eventsTotal: number
  eventsMissed: number
}

export interface EvalReportData {
  modelVersion: string
  aoiId: string
  aucRoc: number
  prAuc: number
  nLabeledCells: number
  confusionMatrix: ConfusionMatrixRow[]
  falseAlarmCost: FalseAlarmCostRow[]
}

function rawEvalReportText(): string {
  const contents = Object.values(evalReportModules)
  if (contents.length === 0 || !contents[0]) {
    throw new Error(
      'evalReport.ts: data/models/eval_report.md was not found via import.meta.glob — has the ' +
        'file moved, or been removed from the gitignore exception (see .gitignore\'s ' +
        "'!data/models/eval_report.md' line)?",
    )
  }
  return contents[0]
}

/** Slices the text strictly between two heading strings (exclusive of both). Throws with a
 * specific, actionable message if either heading is missing — this is the "fail loudly, not
 * silently wrong" behaviour promised in the module docstring. Pass `endHeading: null` to read to
 * the end of the document. */
function sectionBetween(text: string, startHeading: string, endHeading: string | null): string {
  const startIdx = text.indexOf(startHeading)
  if (startIdx === -1) {
    throw new Error(
      `evalReport.ts parser: heading "${startHeading}" not found in eval_report.md — the ` +
        'report\'s structure has changed and this parser (frontend/src/lib/evalReport.ts) needs updating.',
    )
  }
  const afterStart = text.slice(startIdx + startHeading.length)
  if (endHeading === null) return afterStart
  const endIdx = afterStart.indexOf(endHeading)
  if (endIdx === -1) {
    throw new Error(
      `evalReport.ts parser: heading "${endHeading}" not found after "${startHeading}" in ` +
        'eval_report.md — the report\'s structure has changed and this parser needs updating.',
    )
  }
  return afterStart.slice(0, endIdx)
}

/** Parses every Markdown table row (`| a | b | c |`) in a section, skipping the header row and
 * the `|---|---|` separator row. Returns the header row separately so callers can sanity-check
 * column order instead of assuming it. */
function parseMarkdownTable(section: string): { header: string[]; rows: string[][] } {
  const lines = section
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.startsWith('|'))

  const parsed = lines.map((line) =>
    line
      .split('|')
      .slice(1, -1)
      .map((cell) => cell.trim()),
  )

  const isSeparatorRow = (cells: string[]) => cells.every((c) => /^:?-+:?$/.test(c))
  const dataRows = parsed.filter((cells) => !isSeparatorRow(cells))
  const [header, ...rows] = dataRows
  if (!header) {
    throw new Error('evalReport.ts parser: expected a Markdown table in this section, found none.')
  }
  return { header, rows }
}

function parseNumber(raw: string, context: string): number {
  const n = Number.parseFloat(raw)
  if (Number.isNaN(n)) {
    throw new Error(`evalReport.ts parser: could not parse "${raw}" as a number (${context}).`)
  }
  return n
}

/** Parses a "5/14" style cell into its two integer parts. */
function parseFraction(raw: string, context: string): { numerator: number; denominator: number } {
  const match = /^(\d+)\s*\/\s*(\d+)$/.exec(raw.trim())
  if (!match) {
    throw new Error(`evalReport.ts parser: expected "N/M" in "${raw}" (${context}).`)
  }
  return { numerator: Number.parseInt(match[1], 10), denominator: Number.parseInt(match[2], 10) }
}

/** Parses a "17.9%" style cell into 17.9. */
function parsePercent(raw: string, context: string): number {
  const match = /^([\d.]+)\s*%$/.exec(raw.trim())
  if (!match) {
    throw new Error(`evalReport.ts parser: expected "N%" in "${raw}" (${context}).`)
  }
  return Number.parseFloat(match[1])
}

let cached: EvalReportData | null = null

/** Parses `data/models/eval_report.md` into typed data. Memoized — the file is static within a
 * given build (it is read from the committed repo, never refetched at runtime), so there is no
 * reason to re-parse it on every call. */
export function getEvalReport(): EvalReportData {
  if (cached) return cached

  const text = rawEvalReportText()

  const headerMatch = /Model version:\s*`([^`]+)`\s*\|\s*AOI:\s*`([^`]+)`/.exec(text)
  if (!headerMatch) {
    throw new Error(
      'evalReport.ts parser: could not find the "Model version: `...` | AOI: `...`" header line.',
    )
  }
  const [, modelVersion, aoiId] = headerMatch

  const nLabeledMatch = /Final labeled training table:\s*\*\*(\d+)\s*cells\*\*/.exec(text)
  if (!nLabeledMatch) {
    throw new Error('evalReport.ts parser: could not find "Final labeled training table: **N cells**".')
  }
  const nLabeledCells = Number.parseInt(nLabeledMatch[1], 10)

  const aucMatch = /\*\*AUC-ROC:\s*([\d.]+)\*\*/.exec(text)
  if (!aucMatch) throw new Error('evalReport.ts parser: could not find "**AUC-ROC: N**".')
  const aucRoc = Number.parseFloat(aucMatch[1])

  const prAucMatch = /\*\*PR-AUC[^:]*:\s*([\d.]+)\*\*/.exec(text)
  if (!prAucMatch) throw new Error('evalReport.ts parser: could not find "**PR-AUC (...): N**".')
  const prAuc = Number.parseFloat(prAucMatch[1])

  const confusionSection = sectionBetween(
    text,
    '## 5. Confusion matrix at three operating thresholds',
    '## 6. False-alarm-cost table',
  )
  const { header: confusionHeader, rows: confusionRows } = parseMarkdownTable(confusionSection)
  const expectedConfusionHeader = ['Threshold', 'TP', 'FP', 'FN', 'TN']
  if (confusionHeader.join('|') !== expectedConfusionHeader.join('|')) {
    throw new Error(
      `evalReport.ts parser: confusion matrix table header changed — expected ` +
        `${JSON.stringify(expectedConfusionHeader)}, got ${JSON.stringify(confusionHeader)}.`,
    )
  }
  const confusionMatrix: ConfusionMatrixRow[] = confusionRows.map((cells) => ({
    threshold: parseNumber(cells[0], 'confusion matrix threshold'),
    tp: parseNumber(cells[1], 'confusion matrix TP'),
    fp: parseNumber(cells[2], 'confusion matrix FP'),
    fn: parseNumber(cells[3], 'confusion matrix FN'),
    tn: parseNumber(cells[4], 'confusion matrix TN'),
  }))

  const falseAlarmSection = sectionBetween(text, '## 6. False-alarm-cost table', '## 7.')
  const { header: falseAlarmHeader, rows: falseAlarmRows } = parseMarkdownTable(falseAlarmSection)
  const expectedFalseAlarmHeader = [
    'Threshold',
    'Cells flagged',
    '% of labeled cells flagged',
    'Known events caught',
    'Known events missed',
  ]
  if (falseAlarmHeader.join('|') !== expectedFalseAlarmHeader.join('|')) {
    throw new Error(
      `evalReport.ts parser: false-alarm-cost table header changed — expected ` +
        `${JSON.stringify(expectedFalseAlarmHeader)}, got ${JSON.stringify(falseAlarmHeader)}.`,
    )
  }
  const falseAlarmCost: FalseAlarmCostRow[] = falseAlarmRows.map((cells) => {
    const caught = parseFraction(cells[3], 'known events caught')
    const missed = parseFraction(cells[4], 'known events missed')
    if (caught.denominator !== missed.denominator) {
      throw new Error(
        `evalReport.ts parser: "events caught" and "events missed" denominators disagree ` +
          `(${caught.denominator} vs ${missed.denominator}) for threshold ${cells[0]}.`,
      )
    }
    return {
      threshold: parseNumber(cells[0], 'false-alarm-cost threshold'),
      cellsFlagged: parseNumber(cells[1], 'cells flagged'),
      pctCellsFlagged: parsePercent(cells[2], '% of labeled cells flagged'),
      eventsCaught: caught.numerator,
      eventsTotal: caught.denominator,
      eventsMissed: missed.numerator,
    }
  })

  cached = { modelVersion, aoiId, aucRoc, prAuc, nLabeledCells, confusionMatrix, falseAlarmCost }
  return cached
}

/** Merges the confusion-matrix and false-alarm-cost tables by their shared threshold value into
 * one row per operating point — this is what `FalseAlarmSlider` renders per slider position.
 * Throws if a threshold appears in one table but not the other (see module docstring: fail loudly
 * on a structural mismatch rather than silently dropping data). */
export function operatingPoints(data: EvalReportData): FalseAlarmOperatingPoint[] {
  const costByThreshold = new Map(data.falseAlarmCost.map((row) => [row.threshold, row]))
  return data.confusionMatrix.map((cm) => {
    const cost = costByThreshold.get(cm.threshold)
    if (!cost) {
      throw new Error(
        `evalReport.ts parser: threshold ${cm.threshold} appears in the confusion matrix table ` +
          'but not the false-alarm-cost table — the two tables in eval_report.md are expected to ' +
          'cover the same three thresholds.',
      )
    }
    return {
      threshold: cm.threshold,
      tp: cm.tp,
      fp: cm.fp,
      fn: cm.fn,
      tn: cm.tn,
      cellsFlagged: cost.cellsFlagged,
      pctCellsFlagged: cost.pctCellsFlagged,
      eventsCaught: cost.eventsCaught,
      eventsTotal: cost.eventsTotal,
      eventsMissed: cost.eventsMissed,
    }
  })
}

/** Only exported for tests that want to bypass the module-level memoization. */
export function _resetEvalReportCacheForTests(): void {
  cached = null
}
