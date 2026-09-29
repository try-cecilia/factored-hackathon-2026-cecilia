import type { ComponentPropsWithoutRef, ElementType } from 'react'
import { useT } from '../../i18n/context'
import { SidebarSettingsIcon } from './icons'
import { initials } from './initials'
import { useSidebar } from './SidebarContext'
import './SidebarRow.css'
import './SidebarPerson.css'

type OwnProps<C extends ElementType> = {
  /** Makes the footer a link or button (to open settings): `'a'`, or the router's `Link`. Without `as` or `onClick` it is plain text. */
  as?: C
  /** Client: the person's name. Operator: the operator name that comes from their key ("ana.ruiz"), drawn in mono. */
  name: string
  /** Second line of the client footer: segment and country. Not drawn in the operator sidebar. */
  detail?: string
  /** Photo. Without it the avatar shows the initials. */
  avatarSrc?: string
  /** Operator only: green presence dot. */
  online?: boolean
  /** Only for the dev gallery. */
  forceState?: 'hover' | 'focus'
  className?: string
}

export type SidebarPersonProps<C extends ElementType = 'button'> = OwnProps<C> & Omit<ComponentPropsWithoutRef<C>, keyof OwnProps<C> | 'children'>

function Avatar({ name, src, operator, size }: { name: string; src?: string; operator: boolean; size: number }) {
  const style = { width: size, height: size }
  if (src) return <img className="ui-sidebar__avatar" src={src} alt="" width={size} height={size} style={style} draggable={false} />
  return (
    <span className={operator ? 'ui-sidebar__avatar ui-sidebar__avatar--operator' : 'ui-sidebar__avatar ui-sidebar__avatar--initials'} style={style} aria-hidden="true">
      {initials(name)}
    </span>
  )
}

/** Footer of the sidebar: who is signed in. In the rail only the avatar and the settings action stay. */
export function SidebarPerson<C extends ElementType = 'button'>({ as, name, detail, avatarSrc, online, forceState, className, ...rest }: SidebarPersonProps<C>) {
  const t = useT()
  const { variant, collapsed } = useSidebar()
  const operator = variant === 'operator'
  const interactive = as !== undefined || 'onClick' in rest
  const Tag: ElementType = as ?? (interactive ? 'button' : 'div')
  const settings = t('sidebar.person.settings')
  const props = interactive ? { type: Tag === 'button' ? 'button' : undefined, ...rest } : {}

  if (collapsed) {
    return (
      <div className={className ? `ui-sidebar__person-rail ${className}` : 'ui-sidebar__person-rail'}>
        <span className="ui-sidebar__avatar-wrap" role="img" aria-label={name}>
          <Avatar name={name} src={avatarSrc} operator={operator} size={28} />
        </span>
        {interactive && (
          <div className="ui-sidebar__item ui-sidebar__item--rail" data-state={forceState}>
            <Tag {...props} className="ui-sidebar__row" aria-label={`${settings}, ${name}`}>
              <SidebarSettingsIcon style={{ color: 'var(--sb-ink-quiet)' }} />
              <span className="ui-sidebar__tip" aria-hidden="true">{settings}</span>
            </Tag>
          </div>
        )}
      </div>
    )
  }

  const classes = ['ui-sidebar__person', `ui-sidebar__person--${variant}`, interactive && 'ui-sidebar__person--action', className].filter(Boolean).join(' ')
  return (
    <Tag {...props} className={classes} data-state={forceState}>
      <Avatar name={name} src={avatarSrc} operator={operator} size={operator ? 22 : 28} />
      <span className="ui-sidebar__person-text">
        <span className="ui-sidebar__person-name">{name}</span>
        {detail && !operator && <span className="ui-sidebar__person-detail">{detail}</span>}
      </span>
      {online && operator && (
        <>
          <span className="ui-sidebar__presence" aria-hidden="true" />
          <span className="ui-sidebar__sr">{t('sidebar.person.online')}</span>
        </>
      )}
      {interactive && !operator && <SidebarSettingsIcon style={{ color: 'var(--sb-ink-quiet)' }} />}
      {interactive && <span className="ui-sidebar__sr">{settings}</span>}
    </Tag>
  )
}
