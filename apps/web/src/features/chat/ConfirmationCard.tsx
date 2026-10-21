import { AlertTriangle, CalendarCheck, CalendarClock, CalendarX, CheckCircle2 } from 'lucide-react'

import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { currentLanguage } from '@/i18n'
import type { Decision } from '@/lib/api'
import { formatAppointment } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { CardState } from './useChat'

const SPECIALTIES = [
  'general_medicine',
  'cardiology',
  'dentistry',
  'pediatrics',
  'dermatology',
  'gynecology',
  'ophthalmology',
] as const
type Specialty = (typeof SPECIALTIES)[number]

const ICONS = { book: CalendarCheck, reschedule: CalendarClock, cancel: CalendarX }

interface Props {
  card: CardState
  disabled: boolean
  onRespond: (decision: Decision, label: string) => void
}

/** Booking, reschedule or cancellation summary. Nothing changes until the patient confirms. */
export function ConfirmationCard({ card, disabled, onRespond }: Props) {
  const { t } = useTranslation()
  const language = currentLanguage()
  const { details } = card
  const Icon = ICONS[card.kind]
  const when = (iso: string) => formatAppointment(iso, language)
  const specialty = (SPECIALTIES as readonly string[]).includes(details.specialty)
    ? t(`specialties.${details.specialty as Specialty}`)
    : details.specialty

  // `ltr`: codes and phone numbers keep their left-to-right order inside Arabic text.
  const rows: { label: string; value: string; ltr?: boolean }[] = []
  if (details.booking_code) {
    rows.push({ label: t('card.code'), value: details.booking_code, ltr: true })
  }
  rows.push({ label: t('card.doctor'), value: `${details.doctor} · ${specialty}` })
  if (card.kind === 'reschedule' && details.previous_starts_at) {
    rows.push({ label: t('card.previous'), value: when(details.previous_starts_at) })
    rows.push({ label: t('card.newTime'), value: when(details.starts_at) })
  } else {
    rows.push({ label: t('card.when'), value: when(details.starts_at) })
  }
  rows.push({ label: t('card.patient'), value: details.patient_name })
  rows.push({ label: t('card.phone'), value: details.patient_phone, ltr: true })

  const confirmLabel = t(`card.confirm.${card.kind}`)
  const declineLabel = t(`card.decline.${card.kind}`)
  const open = card.status === 'pending' || card.status === 'submitting'

  return (
    <section
      aria-label={t(`card.title.${card.kind}`)}
      className={cn(
        'w-full max-w-sm rounded-2xl border bg-card p-4 shadow-sm',
        !open && 'opacity-90',
      )}
    >
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Icon className="size-4 text-primary" />
        {t(`card.title.${card.kind}`)}
      </h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
        {rows.map(({ label, value, ltr }) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd dir={ltr ? 'ltr' : 'auto'} className={cn(ltr && 'text-start')}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
      {details.late_cancellation_fee_dt && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300">
          <AlertTriangle className="mt-px size-3.5 shrink-0" />
          {t('card.lateFee', { fee: details.late_cancellation_fee_dt })}
        </p>
      )}
      <div className="mt-4">
        {open ? (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant={card.kind === 'cancel' ? 'destructive' : 'default'}
              disabled={disabled || card.status === 'submitting'}
              onClick={() => onRespond('confirm', confirmLabel)}
            >
              {card.status === 'submitting' ? t('card.status.submitting') : confirmLabel}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={disabled || card.status === 'submitting'}
              onClick={() => onRespond('decline', declineLabel)}
            >
              {declineLabel}
            </Button>
          </div>
        ) : (
          <CardStatus card={card} />
        )}
      </div>
    </section>
  )
}

function CardStatus({ card }: { card: CardState }) {
  const { t } = useTranslation()
  if (card.status === 'confirmed') {
    return (
      <p role="status" className="flex items-center gap-1.5 text-sm font-medium text-primary">
        <CheckCircle2 className="size-4" />
        {t('card.status.confirmed')}
        {card.result?.booking_code && (
          <span dir="ltr" className="ms-1 rounded bg-primary/10 px-1.5 py-0.5 font-mono text-xs">
            {card.result.booking_code}
          </span>
        )}
      </p>
    )
  }
  const tone = card.status === 'failed' ? 'text-destructive' : 'text-muted-foreground'
  return (
    <p role="status" className={cn('text-sm', tone)}>
      {card.status === 'submitting' || card.status === 'pending'
        ? null
        : t(`card.status.${card.status}`)}
    </p>
  )
}
