import { useMemo } from 'react'
import { useI18n } from '../i18n/context'
import { formatDate, formatFigure, formatMillions, formatNumber, formatShortDate, type Figure } from './figures'

/** The formatters of `figures.ts`, bound to the page's language. */
export function useFigures() {
  const { locale } = useI18n()
  return useMemo(
    () => ({
      n: (figure: Figure) => formatFigure(figure, locale),
      pct: (figure: Figure) => `${formatFigure(figure, locale)}%`,
      millions: (figure: Figure) => formatMillions(figure, locale),
      /** Milliseconds as seconds with one decimal: 1800 is "1,8". */
      seconds: (figure: Figure) => formatNumber(figure.value / 1000, 1, locale),
      date: (iso: string) => formatDate(iso, locale),
      shortDate: (iso: string) => formatShortDate(iso, locale),
    }),
    [locale],
  )
}
