#!/usr/bin/env node
/**
 * Phase 11 — report production bundle sizes and enforce soft budgets.
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

function main() {
  if (!statSync(DIST, { throwIfNoEntry: false })?.isDirectory()) {
    console.error('dist/ missing — run npm run build first')
    process.exit(1)
  }
  const chunks = collectJs().sort((a, b) => b.bytes - a.bytes)
  const totalJsBytes = chunks.reduce((sum, c) => sum + c.bytes, 0)
  const largest = chunks[0] ?? { name: '(none)', bytes: 0 }

  const report = {
    generatedAt: new Date().toISOString(),
    budgets: BUDGETS,
    totalJsBytes,
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
