import type { Source } from '@/lib/api'

export const CITATION = /\[(\d+)\]/g

/** Numbers cited as [n] in the text that match a known source, in order of first use. */
export function citedNumbers(text: string, sources: Source[]): number[] {
  const known = new Set(sources.map((s) => s.n))
  const cited: number[] = []
  for (const match of text.matchAll(CITATION)) {
    const n = Number(match[1])
    if (known.has(n) && !cited.includes(n)) cited.push(n)
  }
  return cited
}
