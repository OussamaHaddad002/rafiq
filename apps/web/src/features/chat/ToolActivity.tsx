import { AlertCircle, Check, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { ToolActivity as Activity } from '@/lib/api'

const KNOWN_TOOLS = [
  'list_doctors',
  'check_availability',
  'book_appointment',
  'lookup_appointment',
  'reschedule_appointment',
  'cancel_appointment',
  'handoff_to_human',
] as const
type KnownTool = (typeof KNOWN_TOOLS)[number]

function isKnown(name: string): name is KnownTool {
  return (KNOWN_TOOLS as readonly string[]).includes(name)
}

/** What the agent is doing right now, e.g. "Checking availability…" while a tool runs. */
export function ToolActivity({ tools }: { tools: Activity[] }) {
  const { t } = useTranslation()
  const shown = tools.filter((tool) => isKnown(tool.name))
  if (shown.length === 0) return null

  return (
    <ul className="flex flex-col gap-1 px-1 text-xs text-muted-foreground" aria-live="polite">
      {shown.map((tool) => (
        <li key={tool.id} className="flex items-center gap-1.5">
          {tool.status === 'running' && <Loader2 className="size-3 animate-spin" />}
          {tool.status === 'done' && <Check className="size-3 text-primary" />}
          {tool.status === 'error' && <AlertCircle className="size-3 text-destructive" />}
          <span>
            {t(`tools.${tool.name as KnownTool}`)}
            {tool.status === 'running' ? '…' : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}
