import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import { useState } from 'react'

import type { Resource } from '../../api/resources'
import { CapabilitiesPanel } from './CapabilitiesPanel'
import { ResourceOverviewPanel } from './ResourceOverviewPanel'
import { ServiceAssignmentsPanel } from './ServiceAssignmentsPanel'
import { TimeOffPanel } from './TimeOffPanel'
import { WorkingHoursPanel } from './WorkingHoursPanel'
import { DETAIL_TABS } from './useResourcesQueries'

const MASTER_DETAIL_MIN = 720

type ResourceDetailProps = {
  resource: Resource | null
  onBack?: () => void
}

export function ResourceDetail({ resource, onBack }: ResourceDetailProps) {
  const [detailTab, setDetailTab] = useState(0)

  if (!resource) {
    return <Typography color="text.secondary">Select a resource.</Typography>
  }

  return (
    <Stack spacing={2}>
      {onBack ? (
        <Button
          onClick={onBack}
          sx={{
            alignSelf: 'flex-start',
            [`@container resources-md (min-width: ${MASTER_DETAIL_MIN}px)`]: {
              display: 'none',
            },
          }}
        >
          Back to list
        </Button>
      ) : null}
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="h3">{resource.name}</Typography>
        {!resource.active ? <Chip size="small" label="Inactive" /> : null}
      </Stack>
      <Tabs
        value={detailTab}
        onChange={(_, v: number) => setDetailTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Resource detail"
      >
        {DETAIL_TABS.map((label) => (
          <Tab key={label} label={label} />
        ))}
      </Tabs>
      {detailTab === 0 ? <ResourceOverviewPanel resource={resource} /> : null}
      {detailTab === 1 ? <CapabilitiesPanel resource={resource} /> : null}
      {detailTab === 2 ? <WorkingHoursPanel resource={resource} /> : null}
      {detailTab === 3 ? <ServiceAssignmentsPanel resource={resource} /> : null}
      {detailTab === 4 ? <TimeOffPanel resource={resource} /> : null}
    </Stack>
  )
}
