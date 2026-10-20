import { ArrowUp, Square } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

interface ComposerProps {
  isStreaming: boolean
  onSend: (text: string) => void
  onStop: () => void
}

export function Composer({ isStreaming, onSend, onStop }: ComposerProps) {
  const { t } = useTranslation()
  const [text, setText] = useState('')

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (isStreaming || !text.trim()) return
    onSend(text)
    setText('')
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter adds a line; ignore Enter while an IME is composing.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring/40"
    >
      <textarea
        dir="auto"
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={t('chat.placeholder')}
        aria-label={t('chat.placeholder')}
        maxLength={4000}
        className="field-sizing-content max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-muted-foreground"
      />
      {isStreaming ? (
        <Button
          type="button"
          size="icon"
          variant="outline"
          onClick={onStop}
          aria-label={t('chat.stop')}
        >
          <Square className="size-3.5 fill-current" />
        </Button>
      ) : (
        <Button type="submit" size="icon" disabled={!text.trim()} aria-label={t('chat.send')}>
          <ArrowUp />
        </Button>
      )}
    </form>
  )
}
