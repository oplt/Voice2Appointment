#!/usr/bin/env node
/**
 * Phase 5/11 — report production bundle sizes and enforce soft budgets.
 * Distinguishes initial / route / lazy visualization / total JS.
 * Run after `npm run build`. Writes `artifacts/bundle-size.json`.
 */
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const DIST = join(process.cwd(), 'dist')
const ASSETS = join(DIST, 'assets')
const OUT_DIR = join(process.cwd(), 'artifacts')
const OUT = join(OUT_DIR, 'bundle-size.json')

/** Soft budgets (gzip-ish ≈ raw/3; we budget raw bytes for simplicity). */
const BUDGETS = {
  /** Largest single JS chunk */
  maxChunkBytes: 450_000,
  /** Sum of all JS under assets/ */
  maxTotalJsBytes: 1_200_000,
}

function collectJs() {
  const files = readdirSync(ASSETS).filter((f) => f.endsWith('.js'))
  return files.map((name) => {
    const path = join(ASSETS, name)
    const bytes = statSync(path).size
    return { name, bytes }
  })
}

function categorize(name) {
  const lower = name.toLowerCase()
  if (
    lower.includes('analyticscharts') ||
    lower.includes('barchart') ||
    lower.includes('linechart') ||
    lower.includes('charts') ||
    /Charts-/.test(name)
  ) {
    return 'lazyVisualization'
  }
  // Vite typically names the entry index-*.js; route chunks often include page/feature names.
  if (
    /^(index|main)-/.test(name) ||
    lower.includes('vendor') ||
    lower.startsWith('react-') ||
    lower.includes('mui-')
  ) {
    return 'initial'
  }
  return 'route'
}

function main() {
  if (!statSync(DIST, { throwIfNoEntry: false })?.isDirectory()) {
    console.error('dist/ missing — run npm run build first')
    process.exit(1)
  }
  const chunks = collectJs().sort((a, b) => b.bytes - a.bytes)
  const totalJsBytes = chunks.reduce((sum, c) => sum + c.bytes, 0)

  const byCategory = {
    initial: { bytes: 0, chunks: [] },
    route: { bytes: 0, chunks: [] },
    lazyVisualization: { bytes: 0, chunks: [] },
  }

  for (const chunk of chunks) {
    const cat = categorize(chunk.name)
    byCategory[cat].bytes += chunk.bytes
    byCategory[cat].chunks.push(chunk)
  }

  // Prefer HTML modulepreload / script hints for a tighter "initial" estimate when present.
  let htmlInitialHintBytes = null
  try {
    const html = readFileSync(join(DIST, 'index.html'), 'utf8')
    const refs = [
      ...html.matchAll(/(?:src|href)=["'](?:\.\/|\/)?assets\/([^"']+\.js)["']/g),
    ].map((m) => m[1])
    const unique = [...new Set(refs)]
    htmlInitialHintBytes = unique.reduce((sum, name) => {
      const hit = chunks.find((c) => c.name === name)
      return sum + (hit?.bytes ?? 0)
    }, 0)
  } catch {
    htmlInitialHintBytes = null
  }

  const largest = chunks[0] ?? { name: '(none)', bytes: 0 }

  const report = {
    generatedAt: new Date().toISOString(),
    budgets: BUDGETS,
    totalJsBytes,
    initialJsBytes: htmlInitialHintBytes ?? byCategory.initial.bytes,
    routeJsBytes: byCategory.route.bytes,
    lazyVisualizationJsBytes: byCategory.lazyVisualization.bytes,
    categories: byCategory,
    largestChunk: largest,
    chunks,
    htmlBytes: (() => {
      try {
        return readFileSync(join(DIST, 'index.html')).byteLength
      } catch {
        return null
      }
    })(),
  }

  mkdirSync(OUT_DIR, { recursive: true })
  writeFileSync(OUT, `${JSON.stringify(report, null, 2)}\n`)

  console.log('Bundle size report')
  console.log(`  total JS: ${(totalJsBytes / 1024).toFixed(1)} KiB`)
  console.log(
    `  initial (html-referenced): ${((report.initialJsBytes ?? 0) / 1024).toFixed(1)} KiB`,
  )
  console.log(`  route JS: ${(byCategory.route.bytes / 1024).toFixed(1)} KiB`)
  console.log(
    `  lazy visualization JS: ${(byCategory.lazyVisualization.bytes / 1024).toFixed(1)} KiB`,
  )
  console.log(
    `  largest: ${largest.name} (${(largest.bytes / 1024).toFixed(1)} KiB)`,
  )
  console.log(`  wrote ${OUT}`)

  let failed = false
  if (largest.bytes > BUDGETS.maxChunkBytes) {
    console.error(
      `::error::Largest chunk ${largest.name} is ${largest.bytes} bytes (budget ${BUDGETS.maxChunkBytes})`,
    )
    failed = true
  }
  if (totalJsBytes > BUDGETS.maxTotalJsBytes) {
    console.error(
      `::error::Total JS ${totalJsBytes} bytes exceeds budget ${BUDGETS.maxTotalJsBytes}`,
    )
    failed = true
  }
  process.exit(failed ? 1 : 0)
}

main()
