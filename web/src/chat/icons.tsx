// Icons drawn in the Paper file (20x20 grid, 1.6 stroke). Decorative: always aria-hidden.
import type { ReactNode } from 'react'

function Icon({ size = 16, children }: { size?: number; children: ReactNode }) {
  return (
    <svg viewBox="0 0 20 20" width={size} height={size} aria-hidden="true" focusable="false" className="icon">
      {children}
    </svg>
  )
}

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' } as const

export const ChatIcon = () => (
  <Icon>
    <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h9A1.5 1.5 0 0 1 16 5.5v6a1.5 1.5 0 0 1-1.5 1.5H9l-3.5 3v-3h0A1.5 1.5 0 0 1 4 11.5z" {...stroke} />
  </Icon>
)

export const LockIcon = ({ size = 12 }: { size?: number }) => (
  <Icon size={size}>
    <rect x="4.5" y="9" width="11" height="8" rx="2" {...stroke} strokeWidth={1.7} />
    <path d="M7 9V6.5a3 3 0 0 1 6 0V9" {...stroke} strokeWidth={1.7} />
  </Icon>
)

export const SendIcon = () => (
  <Icon size={14}>
    <path d="M10 16V5M5.5 9.5 10 5l4.5 4.5" {...stroke} strokeWidth={1.8} />
  </Icon>
)

export const AlertIcon = () => (
  <Icon>
    <circle cx="10" cy="10" r="7.25" {...stroke} />
    <path d="M10 6.2v4.6M10 13.4v.1" {...stroke} strokeWidth={1.8} />
  </Icon>
)

export const ClockIcon = () => (
  <Icon>
    <circle cx="10" cy="10" r="7.25" {...stroke} />
    <path d="M10 6v4.4l2.8 1.6" {...stroke} />
  </Icon>
)

export const ShieldIcon = () => (
  <Icon>
    <path d="M10 2.8 16 5v4.4c0 3.6-2.4 6.4-6 7.8-3.6-1.4-6-4.2-6-7.8V5z" {...stroke} />
  </Icon>
)

export const OfflineIcon = () => (
  <Icon>
    <path d="M3 8a10 10 0 0 1 14 0M5.6 10.8a6.2 6.2 0 0 1 8.8 0M8.2 13.6a2.4 2.4 0 0 1 3.6 0M4 4l12 12" {...stroke} />
  </Icon>
)

export const CopyIcon = () => (
  <Icon size={14}>
    <rect x="7" y="7" width="9" height="9" rx="2" {...stroke} />
    <path d="M13 7V5.5A1.5 1.5 0 0 0 11.5 4h-6A1.5 1.5 0 0 0 4 5.5v6A1.5 1.5 0 0 0 5.5 13H7" {...stroke} />
  </Icon>
)
