import type { SVGProps } from 'react'

/** 20×20 stroke icons at the small sizes the tables draw them (10–12px). They take their color from `currentColor`. */
export type TableIconProps = Omit<SVGProps<SVGSVGElement>, 'children'> & { size?: number }

function Svg({ size = 10, strokeWidth = 1.8, d, ...rest }: TableIconProps & { d: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flexShrink: 0 }}
      {...rest}
    >
      <path d={d} />
    </svg>
  )
}

export const SortAscIcon = (props: TableIconProps) => <Svg d="M10 15V5M6 9l4-4 4 4" {...props} />
export const SortDescIcon = (props: TableIconProps) => <Svg d="M10 5v10M6 11l4 4 4-4" {...props} />
export const CheckIcon = (props: TableIconProps) => <Svg strokeWidth={2.4} d="M5 10.5l3.2 3.2L15 6.8" {...props} />
export const DashIcon = (props: TableIconProps) => <Svg strokeWidth={2.4} d="M5 10h10" {...props} />
export const CloseIcon = (props: TableIconProps) => <Svg size={12} d="M5 5l10 10M15 5L5 15" {...props} />
