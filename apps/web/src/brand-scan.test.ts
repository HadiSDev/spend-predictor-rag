// @vitest-environment node
/** The retired identities stay retired. */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = dirname(fileURLToPath(import.meta.url))
const SELF = fileURLToPath(import.meta.url)

const RETIRED = [
  /#d7ff53/i,
  /#e9ecea/i,
  /#091315/i,
  /\b9 19 21\b/,
  /spend predictor/i,
  /\bspendly\b/i,
  /erpsaa/i,
]

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) {
      return sourceFiles(path)
    }
    return /\.(tsx?|css)$/.test(name) && path !== SELF ? [path] : []
  })
}

describe('retired brand', () => {
  it('leaves no trace of the old palette or names in apps/web/src', () => {
    const hits = sourceFiles(SRC).flatMap((file) => {
      const text = readFileSync(file, 'utf8')
      return RETIRED.filter((pattern) => pattern.test(text)).map(
        (pattern) => `${relative(SRC, file)}: ${pattern}`,
      )
    })
    expect(hits).toEqual([])
  })
})
