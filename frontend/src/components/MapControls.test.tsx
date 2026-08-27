import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MapControls } from './MapControls'

describe('MapControls', () => {
  it('toggles the risk layer from the layers menu', () => {
    const onLayerChange = () => undefined
    render(<MapControls onZoomIn={() => undefined} onZoomOut={() => undefined} onReset={() => undefined} onLocate={() => undefined} onFullscreen={() => undefined} onLayerChange={onLayerChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'Map layers' }))
    const riskToggle = screen.getByRole('checkbox', { name: 'Risk overlay' })
    expect(riskToggle).toBeChecked()
    fireEvent.click(riskToggle)
    expect(riskToggle).not.toBeChecked()
  })
})
