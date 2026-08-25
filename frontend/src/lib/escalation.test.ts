import { describe, expect, it } from 'vitest'
import { colorForPFail, escalationStage, STAGE_COLOR } from './escalation'

describe('escalationStage', () => {
  it('matches the exact boundaries used by backend/app/decision/stub.py', () => {
    expect(escalationStage(0)).toBe('GREEN')
    expect(escalationStage(0.24)).toBe('GREEN')
    expect(escalationStage(0.25)).toBe('YELLOW')
    expect(escalationStage(0.49)).toBe('YELLOW')
    expect(escalationStage(0.5)).toBe('ORANGE')
    expect(escalationStage(0.74)).toBe('ORANGE')
    expect(escalationStage(0.75)).toBe('RED')
    expect(escalationStage(1)).toBe('RED')
  })
})

describe('colorForPFail', () => {
  it('returns the colour for the corresponding stage', () => {
    expect(colorForPFail(0.1)).toBe(STAGE_COLOR.GREEN)
    expect(colorForPFail(0.9)).toBe(STAGE_COLOR.RED)
  })
})
