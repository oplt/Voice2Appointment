import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { CatalogItem } from '../../api/catalog'
import { CatalogItemActionsMenu } from './CatalogItemActionsMenu'

const item = {
  id: 9,
  name: 'Cut',
  kind: 'service',
  active: true,
  bookable: true,
  sellable: true,
  category_id: null,
  description: null,
  duration_minutes: 30,
  buffer_before_minutes: 0,
  buffer_after_minutes: 0,
  metadata_json: {},
  version: 1,
} as CatalogItem

describe('CatalogItemActionsMenu', () => {
  it('exposes duplicate action', async () => {
    const onDuplicate = vi.fn()
    const user = userEvent.setup()
    render(
      <CatalogItemActionsMenu
        item={item}
        onEdit={vi.fn()}
        onDuplicate={onDuplicate}
        onArchive={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /actions for cut/i }))
    await user.click(await screen.findByText('Duplicate'))
    expect(onDuplicate).toHaveBeenCalledWith(item)
  })
})
