import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState } from 'react'

import type { Resource } from '../../api/resources'
import { ResourceDetail } from './ResourceDetail'

type ResourceListPaneProps = {
  resources: Resource[]
  loading: boolean
  selectedId: number | null
  onSelect: (id: number) => void
}

const MASTER_DETAIL_MIN = 720

export function ResourceListPane({
  resources,
  loading,
  selectedId,
  onSelect,
}: ResourceListPaneProps) {
  const [query, setQuery] = useState('')
  const [detailOpen, setDetailOpen] = useState(false)

  const q = query.trim().toLowerCase()
  const filtered = q
    ? resources.filter(
        (r) =>
          r.name.toLowerCase().includes(q) || r.resource_type.toLowerCase().includes(q),
      )
    : resources

  const effectiveSelectedId =
    selectedId != null && filtered.some((r) => r.id === selectedId)
      ? selectedId
      : (filtered[0]?.id ?? null)
  const selected: Resource | null =
    filtered.find((r) => r.id === effectiveSelectedId) ?? null

  const selectRow = (id: number) => {
    onSelect(id)
    setDetailOpen(true)
  }

  return (
    <Stack spacing={2}>
      <TextField
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search resources"
        fullWidth
        sx={{ maxWidth: 420 }}
      />
      {loading ? (
        <CircularProgress size={28} />
      ) : filtered.length === 0 ? (
        <Typography color="text.secondary">No resources found.</Typography>
      ) : (
        <Box
          sx={{
            containerType: 'inline-size',
            containerName: 'resources-md',
            display: 'grid',
            gap: 2,
            alignItems: 'start',
            gridTemplateColumns: '1fr',
            [`@container resources-md (min-width: ${MASTER_DETAIL_MIN}px)`]: {
              gridTemplateColumns: '280px 1fr',
            },
          }}
        >
          <Box
            sx={{
              display: detailOpen ? 'none' : 'block',
              border: '1px solid var(--border-subtle)',
              borderRadius: 1,
              overflow: 'hidden',
              [`@container resources-md (min-width: ${MASTER_DETAIL_MIN}px)`]: {
                display: 'block',
              },
            }}
          >
            <List disablePadding>
              {filtered.map((row) => (
                <ListItemButton
                  key={row.id}
                  selected={selected?.id === row.id}
                  onClick={() => selectRow(row.id)}
                >
                  <ListItemText
                    primary={row.name}
                    secondary={`${row.resource_type} · cap ${row.capacity}`}
                  />
                </ListItemButton>
              ))}
            </List>
          </Box>

          <Box
            sx={{
              display: detailOpen ? 'block' : 'none',
              border: '1px solid var(--border-subtle)',
              borderRadius: 1,
              p: 2.5,
              bgcolor: 'var(--surface-primary)',
              minHeight: 320,
              [`@container resources-md (min-width: ${MASTER_DETAIL_MIN}px)`]: {
                display: 'block',
              },
            }}
          >
            <ResourceDetail
              resource={selected}
              onBack={() => setDetailOpen(false)}
            />
          </Box>
        </Box>
      )}
    </Stack>
  )
}
