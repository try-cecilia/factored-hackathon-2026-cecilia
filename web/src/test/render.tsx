import { render, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'
import { I18nProvider } from '../i18n/context'
import type { Locale } from '../i18n/locales'

/** Renders inside the i18n provider the kit's components expect. */
export function renderWithI18n(ui: ReactElement, locale: Locale = 'es'): RenderResult {
  return render(<I18nProvider locale={locale}>{ui}</I18nProvider>)
}
