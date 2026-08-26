import { beforeEach, describe, expect, it } from 'vitest'
import { _resetEvalReportCacheForTests, getEvalReport, operatingPoints } from './evalReport'

// These tests parse the REAL committed data/models/eval_report.md (BUILD_PLAN.md task 1.16) —
// not a fixture. This is the whole point of task 5.6's requirement: prove the parser succeeds
// against the actual document on `main`, not a synthetic stand-in that could drift from it.

beforeEach(() => {
  _resetEvalReportCacheForTests()
})

describe('getEvalReport', () => {
  it('parses the real eval_report.md header fields', () => {
    const report = getEvalReport()
    expect(report.modelVersion).toBe('xgb-terrain-v1')
    expect(report.aoiId).toBe('aizawl')
    expect(report.nLabeledCells).toBe(56)
  })

  it('parses the real measured AUC-ROC and PR-AUC (never invented numbers)', () => {
    const report = getEvalReport()
    expect(report.aucRoc).toBeCloseTo(0.696)
    expect(report.prAuc).toBeCloseTo(0.5)
  })

  it('parses the confusion matrix at exactly the three real operating thresholds', () => {
    const report = getEvalReport()
    expect(report.confusionMatrix.map((r) => r.threshold)).toEqual([0.3, 0.5, 0.7])
  })

  it('parses each confusion matrix row correctly against the committed values', () => {
    const report = getEvalReport()
    expect(report.confusionMatrix).toEqual([
      { threshold: 0.3, tp: 5, fp: 5, fn: 9, tn: 37 },
      { threshold: 0.5, tp: 4, fp: 2, fn: 10, tn: 40 },
      { threshold: 0.7, tp: 0, fp: 0, fn: 14, tn: 42 },
    ])
  })

  it('parses the false-alarm-cost table correctly against the committed values', () => {
    const report = getEvalReport()
    expect(report.falseAlarmCost).toEqual([
      { threshold: 0.3, cellsFlagged: 10, pctCellsFlagged: 17.9, eventsCaught: 5, eventsTotal: 14, eventsMissed: 9 },
      { threshold: 0.5, cellsFlagged: 6, pctCellsFlagged: 10.7, eventsCaught: 4, eventsTotal: 14, eventsMissed: 10 },
      { threshold: 0.7, cellsFlagged: 0, pctCellsFlagged: 0.0, eventsCaught: 0, eventsTotal: 14, eventsMissed: 14 },
    ])
  })

  it('memoizes across calls (same object identity)', () => {
    expect(getEvalReport()).toBe(getEvalReport())
  })
})

describe('operatingPoints', () => {
  it('merges the confusion-matrix and false-alarm-cost tables by threshold, in ascending order', () => {
    const points = operatingPoints(getEvalReport())
    expect(points.map((p) => p.threshold)).toEqual([0.3, 0.5, 0.7])
    expect(points[1]).toEqual({
      threshold: 0.5,
      tp: 4,
      fp: 2,
      fn: 10,
      tn: 40,
      cellsFlagged: 6,
      pctCellsFlagged: 10.7,
      eventsCaught: 4,
      eventsTotal: 14,
      eventsMissed: 10,
    })
  })

  it('throws (fails loudly) rather than silently mismatching when a threshold has no counterpart', () => {
    expect(() =>
      operatingPoints({
        modelVersion: 'x',
        aoiId: 'aizawl',
        aucRoc: 0,
        prAuc: 0,
        nLabeledCells: 0,
        confusionMatrix: [{ threshold: 0.9, tp: 0, fp: 0, fn: 0, tn: 0 }],
        falseAlarmCost: [],
      }),
    ).toThrow(/threshold 0.9/)
  })
})
