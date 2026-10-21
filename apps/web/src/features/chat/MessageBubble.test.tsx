import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Source } from '@/lib/api'
import { citedNumbers } from './citationMarkers'
import { MessageBubble } from './MessageBubble'
import type { UiMessage } from './useChat'

const sources: Source[] = [
  {
    n: 1,
    source: 'tarifs.pdf',
    title: 'Tarifs 2026',
    page: 1,
    section: null,
    lang: 'fr',
    excerpt: 'Cardiologie | 80 DT',
  },
  {
    n: 2,
    source: 'faq.md',
    title: 'الأسئلة الشائعة',
    page: null,
    section: 'الدفع',
    lang: 'ar',
    excerpt: 'نقبل الدفع نقدًا وبالبطاقة.',
  },
  {
    n: 3,
    source: 'medecins.pdf',
    title: 'Nos médecins',
    page: 1,
    section: null,
    lang: 'fr',
    excerpt: 'Dr Amira Ben Salah',
  },
]

function assistant(content: string): UiMessage {
  return { id: 'a1', role: 'assistant', content, sources, status: 'done' }
}

describe('citedNumbers', () => {
  it('returns known citations once, in order of first use', () => {
    expect(citedNumbers('A [2] B [1][2] C [9]', sources)).toEqual([2, 1])
  })
})

describe('MessageBubble citations', () => {
  it('turns markers into buttons and lists only the cited sources', () => {
    render(<MessageBubble message={assistant('La cardiologie coûte 80 DT [1]. Paiement [2].')} />)

    expect(screen.getByRole('button', { name: 'Show source 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /tarifs\.pdf/ })).toHaveTextContent('p. 1')
    expect(screen.getByRole('button', { name: /faq\.md/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /medecins\.pdf/ })).not.toBeInTheDocument()
  })

  it('shows the excerpt when a citation is clicked, and hides it on a second click', async () => {
    render(<MessageBubble message={assistant('80 DT [1].')} />)

    await userEvent.click(screen.getByRole('button', { name: 'Show source 1' }))
    expect(screen.getByText('Cardiologie | 80 DT')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /tarifs\.pdf/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    )

    await userEvent.click(screen.getByRole('button', { name: /tarifs\.pdf/ }))
    expect(screen.queryByText('Cardiologie | 80 DT')).not.toBeInTheDocument()
  })

  it('keeps adjacent markers together so they never wrap apart', () => {
    render(<MessageBubble message={assistant('16 DT [1][2].')} />)

    const first = screen.getByRole('button', { name: 'Show source 1' })
    const second = screen.getByRole('button', { name: 'Show source 2' })
    expect(first.parentElement).toBe(second.parentElement)
    expect(first.parentElement).toHaveClass('whitespace-nowrap')
  })

  it('leaves unknown markers as plain text and shows no source list without citations', () => {
    render(<MessageBubble message={assistant('Bonjour [7] !')} />)

    expect(screen.getByText('Bonjour [7] !')).toBeInTheDocument()
    expect(screen.queryByText('Sources')).not.toBeInTheDocument()
  })
})
