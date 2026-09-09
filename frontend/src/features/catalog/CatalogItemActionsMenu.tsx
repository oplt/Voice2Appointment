import MoreVertIcon from '@mui/icons-material/MoreVert'
import IconButton from '@mui/material/IconButton'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import { useId, useState } from 'react'

import type { CatalogItem } from '../../api/catalog'

type CatalogItemActionsMenuProps = {
  item: CatalogItem
  onEdit: (item: CatalogItem) => void
  onDuplicate: (item: CatalogItem) => void
  onArchive: (item: CatalogItem) => void
}

export function CatalogItemActionsMenu({
  item,
  onEdit,
  onDuplicate,
  onArchive,
}: CatalogItemActionsMenuProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const menuId = useId()
  const open = Boolean(anchorEl)

  return (
    <>
      <IconButton
        size="small"
        aria-label={`Actions for ${item.name}`}
        aria-controls={open ? menuId : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        onClick={(event) => {
          event.stopPropagation()
          setAnchorEl(event.currentTarget)
        }}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu
        id={menuId}
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        onClick={(event) => event.stopPropagation()}
      >
        <MenuItem
          onClick={() => {
            setAnchorEl(null)
            onEdit(item)
          }}
        >
          <ListItemText>Edit</ListItemText>
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchorEl(null)
            onDuplicate(item)
          }}
        >
          <ListItemText>Duplicate</ListItemText>
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchorEl(null)
            onArchive(item)
          }}
        >
          <ListItemText>Archive</ListItemText>
        </MenuItem>
      </Menu>
    </>
  )
}
