import type { ReactNode, SVGProps } from 'react'

/** 20×20 stroke icons drawn at 14px in the Paper buttons. They take their color from `currentColor`. */
export type IconProps = Omit<SVGProps<SVGSVGElement>, 'children'> & { size?: number }

function Icon({ size = 14, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
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

export const PlusIcon = (props: IconProps) => <Icon {...props}><path d="M10 4v12M4 10h12" /></Icon>
export const ArrowUpIcon = (props: IconProps) => <Icon {...props}><path d="M10 16V5M5.5 9.5 10 5l4.5 4.5" /></Icon>
export const ArrowRightIcon = (props: IconProps) => <Icon {...props}><path d="M4 10h11M11 6l4 4-4 4" /></Icon>
export const MenuIcon = (props: IconProps) => <Icon {...props}><path d="M4 6h12M4 10h12M4 14h12" /></Icon>
export const CopyIcon = (props: IconProps) => (
  <Icon strokeWidth={1.6} {...props}>
    <rect x="7" y="7" width="9" height="9" rx="1.8" />
    <path d="M13 7V5.8A1.8 1.8 0 0 0 11.2 4H5.8A1.8 1.8 0 0 0 4 5.8v5.4A1.8 1.8 0 0 0 5.8 13H7" />
  </Icon>
)
export const TrashIcon = (props: IconProps) => (
  <Icon strokeWidth={1.6} {...props}><path d="M5 6h10M8 6V4.5h4V6M6.5 6l.6 9.5h5.8l.6-9.5" /></Icon>
)
