import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PageHeader } from '../components/PageHeader'

describe('PageHeader', () => {
  it('renders title and subtitle', () => {
    render(<PageHeader title="Dashboard" subtitle="Overview of calls and bookings" />)
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByText('Overview of calls and bookings')).toBeInTheDocument()
  })
})
