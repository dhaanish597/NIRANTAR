import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { WhatIfWorkspace } from './WhatIfWorkspace'

describe('WhatIfWorkspace', () => {
  it('renders the What-if Simulator heading and its rainfall control', () => {
    render(<WhatIfWorkspace />)
    expect(screen.getByText('What-if Simulator')).toBeInTheDocument()
    expect(screen.getByLabelText('Total rainfall in millimetres')).toBeInTheDocument()
  })
})
