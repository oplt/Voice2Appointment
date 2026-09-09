import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import { useState } from 'react'

import { PageHeader } from '../../components/PageHeader'
import { CapabilitiesChecklistPanel } from './CapabilitiesChecklistPanel'
import { HandoffPanel } from './HandoffPanel'
import { IndustryProfilePanel } from './IndustryProfilePanel'
import { InstructionsPanel } from './InstructionsPanel'
import { KnowledgePanel } from './KnowledgePanel'
import { LanguagesPanel } from './LanguagesPanel'
import { VoicePanel } from './VoicePanel'

export function AgentView() {
  const [tab, setTab] = useState(0)

  return (
    <Stack spacing={3}>
      <PageHeader
        title="Agent"
        subtitle="Voice, languages, handoff, instructions, and knowledge."
      />
      <Tabs
        value={tab}
        onChange={(_, value: number) => setTab(value)}
        variant="scrollable"
        scrollButtons="auto"
        aria-label="Agent sections"
      >
        <Tab label="Voice" />
        <Tab label="Languages" />
        <Tab label="Handoff" />
        <Tab label="Instructions" />
        <Tab label="Knowledge" />
        <Tab label="Industry profile" />
        <Tab label="Capabilities" />
      </Tabs>

      {tab === 0 ? <VoicePanel /> : null}
      {tab === 1 ? <LanguagesPanel /> : null}
      {tab === 2 ? <HandoffPanel /> : null}
      {tab === 3 ? <InstructionsPanel /> : null}
      {tab === 4 ? <KnowledgePanel /> : null}
      {tab === 5 ? <IndustryProfilePanel /> : null}
      {tab === 6 ? <CapabilitiesChecklistPanel /> : null}
    </Stack>
  )
}
