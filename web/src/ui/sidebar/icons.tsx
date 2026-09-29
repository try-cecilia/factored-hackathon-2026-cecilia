import type { ReactNode } from 'react'
import type { IconProps } from '../icons'

/** Sidebar icons, drawn as in Paper on a 20×20 grid at 16px (15px in the row menu) with a 1.5 stroke. Color is `currentColor`. */
function Icon({ size = 16, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flexShrink: 0 }}
      {...rest}
    >
      {children}
    </svg>
  )
}

const compose = 'M11.5 4.5H6A2 2 0 0 0 4 6.5v7.5a2 2 0 0 0 2 2h7.5a2 2 0 0 0 2-2V8.5M9 11l6.2-6.2a1.3 1.3 0 0 1 1.8 1.8L10.8 12.8 8.5 13.2z'

/** Pencil over a sheet: new chat, and "Rename" in the row menu. */
export const SidebarComposeIcon = (props: IconProps) => <Icon {...props}><path d={compose} /></Icon>
export const SidebarSearchIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="9" cy="9" r="5.2" />
    <path d="M13 13l3.5 3.5" />
  </Icon>
)
export const SidebarChatIcon = (props: IconProps) => (
  <Icon {...props}><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h9A1.5 1.5 0 0 1 16 5.5v6a1.5 1.5 0 0 1-1.5 1.5H9l-3.5 3v-3A1.5 1.5 0 0 1 4 11.5z" /></Icon>
)
/** Receipt: the customer's cases (handoffs and traces). */
export const SidebarCasesIcon = (props: IconProps) => (
  <Icon {...props}><path d="M5 4.5h10v11l-2-1.3-1.6 1.3L10 14.2 8.6 15.5 7 14.2 5 15.5z" /></Icon>
)
export const SidebarSettingsIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="10" cy="10" r="2.6" />
    <path d="M10 3.5v1.7M10 14.8v1.7M3.5 10h1.7M14.8 10h1.7M5.4 5.4l1.2 1.2M13.4 13.4l1.2 1.2M14.6 5.4l-1.2 1.2M6.6 13.4l-1.2 1.2" />
  </Icon>
)
/** Panel with its left rail: collapse and expand the sidebar. */
export const SidebarToggleIcon = (props: IconProps) => (
  <Icon {...props}>
    <rect x="3.5" y="4.5" width="13" height="11" rx="2.2" />
    <path d="M8 4.8v10.4" />
  </Icon>
)
/** Three dots: the row menu trigger. Filled, as in Paper. */
export const SidebarMoreIcon = (props: IconProps) => (
  <Icon stroke="none" fill="currentColor" {...props}>
    <circle cx="5" cy="10" r="1.3" />
    <circle cx="10" cy="10" r="1.3" />
    <circle cx="15" cy="10" r="1.3" />
  </Icon>
)
export const SidebarRenameIcon = (props: IconProps) => <Icon size={15} {...props}><path d={compose} /></Icon>
export const SidebarPinIcon = (props: IconProps) => (
  <Icon size={15} strokeWidth={1.4} {...props}><path d="M10 3.5l1.8 4 4.2.4-3.2 2.8 1 4.3L10 12.8 6.2 15l1-4.3L4 7.9l4.2-.4z" /></Icon>
)
export const SidebarArchiveIcon = (props: IconProps) => (
  <Icon size={15} strokeWidth={1.4} {...props}><path d="M4 6.5h12v2H4zM5 8.5h10v7H5zM8 11.5h4" /></Icon>
)
export const SidebarDeleteIcon = (props: IconProps) => (
  <Icon size={15} {...props}><path d="M5 6h10M8 6V4.5h4V6M6.5 6l.6 9.5h5.8l.6-9.5" /></Icon>
)
