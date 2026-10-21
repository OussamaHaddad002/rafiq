import { FileText } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { Source } from '@/lib/api'
import { cn } from '@/lib/utils'
import { CITATION } from './citationMarkers'

/** Text with [n] markers that match a source turned into small buttons. */
export function CitedText({
  text,
  sources,
  active,
  onCite,
}: {
  text: string
  sources: Source[]
  active: number | null
  onCite: (n: number) => void
}) {
  const known = new Set(sources.map((s) => s.n))
  const nodes: ReactNode[] = []
  // Adjacent markers like [1][3] form one group that never wraps across lines.
  let group: ReactNode[] = []
  let last = 0
  const flushGroup = () => {
    if (group.length > 0) {
      nodes.push(
        <span key={`group-${last}`} className="whitespace-nowrap">
          {group}
        </span>,
      )
      group = []
    }
  }
  for (const match of text.matchAll(CITATION)) {
    const n = Number(match[1])
    if (!known.has(n)) continue
    if (match.index !== last) {
      flushGroup()
      nodes.push(text.slice(last, match.index))
    }
    group.push(
      <CitationMarker key={`${match.index}-${n}`} n={n} active={active === n} onClick={onCite} />,
    )
    last = match.index + match[0].length
  }
  flushGroup()
  nodes.push(text.slice(last))
  return <>{nodes}</>
}

function CitationMarker({
  n,
  active,
  onClick,
}: {
  n: number
  active: boolean
  onClick: (n: number) => void
}) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      onClick={() => onClick(n)}
      aria-label={t('chat.citation', { n })}
      className={cn(
        'mx-0.5 inline-flex h-4 min-w-4 -translate-y-1.5 items-center justify-center rounded px-1 text-[10px] font-semibold transition-colors',
        active
          ? 'bg-primary text-primary-foreground'
          : 'bg-primary/15 text-primary hover:bg-primary/25',
      )}
    >
      {n}
    </button>
  )
}

export function SourceList({
  sources,
  cited,
  active,
  onToggle,
}: {
  sources: Source[]
  cited: number[]
  active: number | null
  onToggle: (n: number) => void
}) {
  const { t } = useTranslation()
  const shown = cited
    .map((n) => sources.find((s) => s.n === n))
    .filter((s): s is Source => s !== undefined)
  if (shown.length === 0) return null
  const open = shown.find((s) => s.n === active)

  return (
    <div className="flex flex-col gap-2 px-1">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-muted-foreground">{t('chat.sources')}</span>
        {shown.map((source) => (
          <button
            key={source.n}
            type="button"
            aria-expanded={active === source.n}
            onClick={() => onToggle(source.n)}
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors',
              active === source.n ? 'border-primary bg-primary/10' : 'bg-card hover:bg-muted',
            )}
          >
            <span className="font-semibold text-primary">{source.n}</span>
            <FileText className="size-3 text-muted-foreground" />
            <span dir="ltr">{source.source}</span>
            {source.page !== null && (
              <span className="text-muted-foreground">
                · {t('chat.page', { page: source.page })}
              </span>
            )}
          </button>
        ))}
      </div>
      {open && (
        <blockquote
          dir="auto"
          className="max-h-56 overflow-y-auto rounded-xl border bg-muted/50 px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground"
        >
          {/* PDF pages usually start with the document title already. */}
          {!open.excerpt.startsWith(open.title) && (
            <p className="mb-1 font-medium text-foreground">
              {open.title}
              {open.section ? ` · ${open.section}` : ''}
            </p>
          )}
          {open.excerpt}
        </blockquote>
      )}
    </div>
  )
}
