import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { useId, useState, type ReactNode } from 'react'

type SeriesTableProps = {
  title: string
  summary: string
  labels: string[]
  values: number[]
  valueLabel?: string
  children: ReactNode
}

/** Chart with concise summary + toggleable semantic data table (P5-05/P5-V05). */
export function ChartWithTable({
  title,
  summary,
  labels,
  values,
  valueLabel = 'Value',
  children,
}: SeriesTableProps) {
  const [showTable, setShowTable] = useState(false)
  const tableId = useId()
  const titleId = useId()

  return (
    <Stack spacing={1} component="section" aria-labelledby={titleId}>
      <Stack
        direction="row"
        spacing={1}
        useFlexGap
        sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}
      >
        <Typography id={titleId} variant="h3">
          {title}
        </Typography>
        <Button
          size="small"
          variant="text"
          onClick={() => setShowTable((v) => !v)}
          aria-expanded={showTable}
          aria-controls={tableId}
        >
          {showTable ? 'Hide table' : 'Show table'}
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {summary}
      </Typography>
      <div aria-hidden={showTable}>{children}</div>
      {showTable ? (
        <TableContainer id={tableId}>
          <Table size="small" aria-label={`${title} data table`}>
            <TableHead>
              <TableRow>
                <TableCell>Label</TableCell>
                <TableCell align="right">{valueLabel}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {labels.map((label, idx) => (
                <TableRow key={`${label}-${idx}`}>
                  <TableCell>{label}</TableCell>
                  <TableCell align="right">{values[idx] ?? 0}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : null}
    </Stack>
  )
}

type HeatmapTableProps = {
  title: string
  summary: string
  weekdays: string[]
  hours: number[]
  matrix: number[][]
  children: ReactNode
}

/** Heatmap wrapper with full zero-inclusive table parity. */
export function HeatmapWithTable({
  title,
  summary,
  weekdays,
  hours,
  matrix,
  children,
}: HeatmapTableProps) {
  const [showTable, setShowTable] = useState(false)
  const tableId = useId()
  const titleId = useId()
  const rows = weekdays.flatMap((day, rowIdx) =>
    hours.map((hour) => ({
      day,
      hour,
      value: matrix[rowIdx]?.[hour] ?? 0,
    })),
  )

  return (
    <Stack spacing={1} component="section" aria-labelledby={titleId}>
      <Stack
        direction="row"
        spacing={1}
        useFlexGap
        sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}
      >
        <Typography id={titleId} variant="h3">
          {title}
        </Typography>
        <Button
          size="small"
          variant="text"
          onClick={() => setShowTable((v) => !v)}
          aria-expanded={showTable}
          aria-controls={tableId}
        >
          {showTable ? 'Hide table' : 'Show table'}
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {summary}
      </Typography>
      <div aria-hidden={showTable}>{children}</div>
      {showTable ? (
        <TableContainer id={tableId}>
          <Table size="small" aria-label={`${title} data table`}>
            <TableHead>
              <TableRow>
                <TableCell>Weekday</TableCell>
                <TableCell>Hour</TableCell>
                <TableCell align="right">Calls</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((cell) => (
                <TableRow key={`${cell.day}-${cell.hour}`}>
                  <TableCell>{cell.day}</TableCell>
                  <TableCell>{cell.hour}:00</TableCell>
                  <TableCell align="right">{cell.value}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : null}
    </Stack>
  )
}
