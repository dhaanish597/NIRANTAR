import { describe, expect, it } from 'vitest'
import {
  deathTollInfo,
  formatAoiIdFallback,
  getScenarioDetail,
  type ScenarioFile,
  whatWentWrongLine,
} from './scenarioDetails'

describe('getScenarioDetail', () => {
  it('loads the committed _smoke.json scenario file directly (no network call)', () => {
    const detail = getScenarioDetail('_smoke')
    expect(detail).toBeDefined()
    expect(detail?.aoi_id).toBe('aizawl')
    expect(detail?.held_out_of_training).toBe(false)
    expect(detail?.provenance.confidence).toBe('fabricated')
  })

  it('returns undefined for an id no scenario file declares', () => {
    expect(getScenarioDetail('does-not-exist')).toBeUndefined()
  })
})

describe('deathTollInfo', () => {
  it('returns null when the scenario has no ground_truth block (e.g. _smoke)', () => {
    expect(deathTollInfo(getScenarioDetail('_smoke'))).toBeNull()
  })

  it('returns null for undefined detail', () => {
    expect(deathTollInfo(undefined)).toBeNull()
  })

  it('reads deaths and source_note straight from ground_truth.outcome, never fabricating one', () => {
    const detail: ScenarioFile = {
      id: 'aizawl-2024',
      aoi_id: 'aizawl',
      held_out_of_training: true,
      provenance: { confidence: 'reconstructed' },
      ground_truth: {
        outcome: {
          deaths: '27–34 (state total; 33 bodies recovered per academic study)',
          source_note: 'Report as a range with source; do not assert a single figure.',
        },
      },
    }
    expect(deathTollInfo(detail)).toEqual({
      deaths: '27–34 (state total; 33 bodies recovered per academic study)',
      sourceNote: 'Report as a range with source; do not assert a single figure.',
    })
  })

  it('still returns the death figure when source_note is absent, with sourceNote null', () => {
    const detail: ScenarioFile = {
      id: 'x',
      aoi_id: 'aizawl',
      held_out_of_training: true,
      provenance: {},
      ground_truth: { outcome: { deaths: '61' } },
    }
    expect(deathTollInfo(detail)).toEqual({ deaths: '61', sourceNote: null })
  })
})

describe('whatWentWrongLine', () => {
  it('returns null for a scenario with no ground_truth or narration (e.g. _smoke)', () => {
    expect(whatWentWrongLine(getScenarioDetail('_smoke'))).toBeNull()
  })

  it('prefers the first official warning note', () => {
    const detail: ScenarioFile = {
      id: 'x',
      aoi_id: 'aizawl',
      held_out_of_training: true,
      provenance: {},
      ground_truth: {
        official_warnings: [{ t: 't', issuer: 'IMD', level: 'red', note: 'No slope-specific warning issued' }],
        road_events: [{ t: 't', road: 'NH-6', effect: 'severed', consequence: 'Aizawl isolated' }],
      },
    }
    expect(whatWentWrongLine(detail)).toBe('No slope-specific warning issued')
  })

  it('falls back to the first road event consequence when there is no warning note', () => {
    const detail: ScenarioFile = {
      id: 'x',
      aoi_id: 'aizawl',
      held_out_of_training: true,
      provenance: {},
      ground_truth: {
        road_events: [{ t: 't', road: 'NH-6', effect: 'severed', consequence: 'Aizawl isolated' }],
      },
    }
    expect(whatWentWrongLine(detail)).toBe('Aizawl isolated')
  })

  it('falls back to the first narration line when there is no ground_truth', () => {
    const detail: ScenarioFile = {
      id: 'x',
      aoi_id: 'aizawl',
      held_out_of_training: true,
      provenance: {},
      narration: [{ t: 't', text: 'Rain builds through the night.' }],
    }
    expect(whatWentWrongLine(detail)).toBe('Rain builds through the night.')
  })
})

describe('formatAoiIdFallback', () => {
  it('title-cases a plain aoi id', () => {
    expect(formatAoiIdFallback('aizawl')).toBe('Aizawl')
  })

  it('splits on hyphens and underscores', () => {
    expect(formatAoiIdFallback('south_lhonak')).toBe('South Lhonak')
    expect(formatAoiIdFallback('mangan-sikkim')).toBe('Mangan Sikkim')
  })
})
