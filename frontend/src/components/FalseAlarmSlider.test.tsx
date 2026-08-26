import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FalseAlarmSlider } from './FalseAlarmSlider'

describe('FalseAlarmSlider', () => {
  it('defaults to the middle real threshold (0.50) and shows its real numbers', () => {
    render(<FalseAlarmSlider />)
    expect(screen.getByText('Threshold 0.50')).toBeInTheDocument()
    // eval_report.md §6, threshold 0.50 row: 6 cells flagged, 4/14 caught, 10 missed.
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('4/14')).toBeInTheDocument()
  })

  it('moving the slider to threshold 0.30 shows that row\'s real numbers (5/14 caught)', () => {
    render(<FalseAlarmSlider />)
    const slider = screen.getByRole('slider', { name: 'Operating threshold' })
    fireEvent.change(slider, { target: { value: '0' } })
    expect(screen.getByText('Threshold 0.30')).toBeInTheDocument()
    expect(screen.getByText('5/14')).toBeInTheDocument()
  })

  it('moving the slider to threshold 0.70 shows zero cells flagged and zero events caught', () => {
    render(<FalseAlarmSlider />)
    const slider = screen.getByRole('slider', { name: 'Operating threshold' })
    fireEvent.change(slider, { target: { value: '2' } })
    expect(screen.getByText('Threshold 0.70')).toBeInTheDocument()
    expect(screen.getByText('0/14')).toBeInTheDocument()
  })

  it('only exposes the three measured thresholds as slider steps (no interpolation)', () => {
    render(<FalseAlarmSlider />)
    const slider = screen.getByRole('slider', { name: 'Operating threshold' }) as HTMLInputElement
    expect(slider.min).toBe('0')
    expect(slider.max).toBe('2')
    expect(slider.step).toBe('1')
  })

  it('cites the source document and its illustrative-only caveat', () => {
    render(<FalseAlarmSlider />)
    expect(screen.getByText(/data\/models\/eval_report\.md/)).toBeInTheDocument()
    expect(screen.getByText(/no interpolation/i)).toBeInTheDocument()
  })
})
