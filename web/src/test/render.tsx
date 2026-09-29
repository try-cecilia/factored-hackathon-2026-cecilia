import { render, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'
import { I18nProvider } from '../i18n/context'
import { es } from '../i18n/es'
import type { Locale } from '../i18n/locales'
import { pt } from '../i18n/pt'

/** Every text of both languages: a test draws any area. */
export const dictionaries = { es, pt }

/** Renders inside the i18n provider the kit's components expect. */
export function renderWithI18n(ui: ReactElement, locale: Locale = 'es'): RenderResult {
  return render(<I18nProvider locale={locale} messages={dictionaries[locale]}>{ui}</I18nProvider>)
}
