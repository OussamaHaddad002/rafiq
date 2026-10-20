import 'i18next'

import type en from './locales/en.json'

// Type-checked translation keys: t('chat.sendd') is a compile error.
declare module 'i18next' {
  interface CustomTypeOptions {
    resources: { translation: typeof en }
  }
}
