import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './Button.css'
import { Spinner } from './Spinner'

export type ButtonVariant = 'primary' | 'destructive' | 'ghost' | 'outline'
/** lg 40 (landing, sign-in), md 32 (chat, cards), sm 28 (tables, sidebars), xs 24 (operator desk). */
export type ButtonSize = 'lg' | 'md' | 'sm' | 'xs'

type Common = {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Shows the spinner and blocks clicks. The label stays, in progressive form ("Confirming"). */
  loading?: boolean
  /** Only for the dev gallery: draws a state without needing the pointer or the keyboard. */
  forceState?: 'hover' | 'pressed' | 'focus'
}

type ButtonProps = Common &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> & {
    children: ReactNode
    leadingIcon?: ReactNode
    trailingIcon?: ReactNode
    /** Pill with a count, e.g. open cases. It is read as part of the label. */
    count?: number
    /** Ghost on a tonal fill (`fill-muted`), for the secondary action next to a primary one ("Keep it", "Continue"). */
    tinted?: boolean
    /** Quieter text for the least important action of a group ("Release" in the operator trio). */
    muted?: boolean
  }

function classes(props: Common & { className?: string; iconOnly?: boolean; muted?: boolean; tinted?: boolean }) {
  const { variant = 'primary', size = 'md', loading, className, iconOnly, muted, tinted } = props
  return [
    'ui-btn',
    `ui-btn--${variant}`,
    `ui-btn--${size}`,
    iconOnly && 'ui-btn--icon',
    muted && 'ui-btn--muted',
    tinted && 'ui-btn--tinted',
    loading && 'ui-btn--loading',
    className,
  ]
    .filter(Boolean)
    .join(' ')
}

export function Button({
  variant,
  size,
  loading,
  forceState,
  leadingIcon,
  trailingIcon,
  count,
  muted,
  tinted,
  className,
  children,
  type = 'button',
  disabled,
  onClick,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={classes({ variant, size, loading, className, muted, tinted })}
      data-state={forceState}
      disabled={disabled}
      aria-busy={loading || undefined}
      onClick={loading ? undefined : onClick}
      data-leading={leadingIcon ? '' : undefined}
      data-trailing={trailingIcon ? '' : undefined}
    >
      {loading ? <Spinner /> : leadingIcon}
      <span>{children}</span>
      {trailingIcon}
      {count !== undefined && <span className="ui-btn__count">{count}</span>}
    </button>
  )
}

type IconButtonProps = Common &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'aria-label'> & {
    /** Icon buttons have no text, so the accessible name is required. */
    label: string
    icon: ReactNode
  }

export function IconButton({ variant, size, loading, forceState, label, icon, className, type = 'button', onClick, ...rest }: IconButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={classes({ variant, size, loading, className, iconOnly: true })}
      data-state={forceState}
      aria-label={label}
      aria-busy={loading || undefined}
      onClick={loading ? undefined : onClick}
    >
      {loading ? <Spinner /> : icon}
    </button>
  )
}
