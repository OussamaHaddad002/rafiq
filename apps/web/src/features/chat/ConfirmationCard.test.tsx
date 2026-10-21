import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import { formatAppointment } from '@/lib/datetime'
import { ConfirmationCard } from './ConfirmationCard'
import type { CardState } from './useChat'

function card(overrides: Partial<CardState> = {}): CardState {
  return {
    action_id: 'a-1',
    kind: 'book',
    status: 'pending',
    expires_at: '2026-10-21T08:15:00Z',
    result: null,
    details: {
      doctor: 'Dr Amira Ben Salah',
      specialty: 'cardiology',
      starts_at: '2026-10-23T10:00:00+01:00',
      patient_name: 'Salma Ben Ali',
      patient_phone: '+216•••••123',
    },
    ...overrides,
  }
}

describe('formatAppointment', () => {
  it('formats in clinic time whatever the browser time zone', () => {
    expect(formatAppointment('2026-10-23T09:00:00Z', 'en')).toBe('Friday 23 October at 10:00')
  })

  it('uses 24-hour time in every language, like the chat', () => {
    const arabic = formatAppointment('2026-10-26T15:30:00Z', 'ar')
    expect(arabic).toContain('16:30')
    expect(arabic).not.toMatch(/[صم]$/) // no 12-hour AM/PM marker
    expect(formatAppointment('2026-10-26T15:30:00Z', 'fr')).toContain('16:30')
  })
})

describe('ConfirmationCard', () => {
  it('shows the booking details in the interface language and sends the decision', async () => {
    await i18n.changeLanguage('fr')
    const onRespond = vi.fn()
    render(<ConfirmationCard card={card()} disabled={false} onRespond={onRespond} />)

    expect(screen.getByRole('region', { name: 'Confirmez votre rendez-vous' })).toBeInTheDocument()
    expect(screen.getByText('Dr Amira Ben Salah · Cardiologie')).toBeInTheDocument()
    expect(screen.getByText(/vendredi 23 octobre/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    expect(onRespond).toHaveBeenCalledWith('confirm', 'Confirmer')
  })

  it('warns about the late-cancellation fee and uses cancel wording', async () => {
    const onRespond = vi.fn()
    render(
      <ConfirmationCard
        card={card({
          kind: 'cancel',
          details: { ...card().details, booking_code: 'RFQ-7K3PX', late_cancellation_fee_dt: 20 },
        })}
        disabled={false}
        onRespond={onRespond}
      />,
    )

    expect(
      screen.getByText('Cancelling less than 24 hours before costs 20 DT.'),
    ).toBeInTheDocument()
    expect(screen.getByText('RFQ-7K3PX')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Keep it' }))
    expect(onRespond).toHaveBeenCalledWith('decline', 'Keep it')
  })

  it('shows the outcome instead of buttons once answered', () => {
    render(
      <ConfirmationCard
        card={card({ status: 'confirmed', result: { booking_code: 'RFQ-7K3PX' } })}
        disabled={false}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('ConfirmedRFQ-7K3PX')
  })

  it('cannot be answered while another reply is streaming', () => {
    render(<ConfirmationCard card={card()} disabled onRespond={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled()
  })
})
