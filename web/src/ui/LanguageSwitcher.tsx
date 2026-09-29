import { useRouter } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n, useT } from '../i18n/context'
import { localeNames, locales, type Locale } from '../i18n/locales'
import { setLocale } from '../server/locale.functions'
import './LanguageSwitcher.css'

type Props = {
  /** Called with the chosen language. By default it saves the preference cookie on the server and reloads the page data. */
  onChange?: (locale: Locale) => void | Promise<void>
  className?: string
}

/** Segmented control, one button per language. Each name is written in its own language and marked with `lang`. */
export function LanguageSwitcher({ onChange, className }: Props) {
  const { locale } = useI18n()
  const t = useT()
  const router = useRouter()
  const [pending, setPending] = useState<Locale | null>(null)

  async function choose(next: Locale) {
    if (next === locale || pending) return
    setPending(next)
    try {
      if (onChange) await onChange(next)
      else {
        await setLocale({ data: next })
        await router.invalidate()
      }
    } finally {
      setPending(null)
    }
  }

  return (
    <div className={className ? `ui-lang ${className}` : 'ui-lang'} role="group" aria-label={t('common.language.label')}>
      {locales.map((option) => (
        <button
          key={option}
          type="button"
          lang={option}
          className="ui-lang__option"
          aria-pressed={option === locale}
          aria-busy={pending === option || undefined}
          onClick={() => void choose(option)}
        >
          {localeNames[option]}
        </button>
      ))}
    </div>
  )
}
