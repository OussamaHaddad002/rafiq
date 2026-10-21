import type { Language } from '@/lib/api'

export const CLINIC_TIME_ZONE = 'Africa/Tunis'

const LOCALES: Record<Language, string> = { ar: 'ar-TN', fr: 'fr-FR', en: 'en-GB' }

/** "Friday 23 October, 10:00" in the patient's language, always in clinic time. */
export function formatAppointment(iso: string, language: Language): string {
  return new Intl.DateTimeFormat(LOCALES[language], {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23', // 16:30 like the chat, not "04:30 م" (ar-TN defaults to 12-hour time)
    timeZone: CLINIC_TIME_ZONE,
  }).format(new Date(iso))
}
