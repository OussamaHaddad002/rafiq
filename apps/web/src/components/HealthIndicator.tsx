import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { getHealth } from '@/lib/api'
import { cn } from '@/lib/utils'

export function HealthIndicator() {
  const { t } = useTranslation()
  const { data, isError } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30_000,
    retry: false,
  })
  const online = !isError && data?.status === 'ok'
  const label = online ? t('app.online') : t('app.offline')

  return (
    <span title={label} className="relative flex size-2.5">
      {online && (
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />
      )}
      <span
        className={cn(
          'relative inline-flex size-2.5 rounded-full',
          online ? 'bg-emerald-500' : 'bg-muted-foreground',
        )}
      />
      <span className="sr-only">{label}</span>
    </span>
  )
}
