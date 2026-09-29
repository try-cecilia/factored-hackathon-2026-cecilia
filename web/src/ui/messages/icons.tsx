import type { ReactNode, SVGProps } from 'react'

/** The small glyphs of the chat messages, drawn on Paper's 20×20 grid. They take their color from `currentColor`. */
export type MessageIconProps = Omit<SVGProps<SVGSVGElement>, 'children'> & { size?: number }

function Glyph({ size = 15, strokeWidth = 1.6, children, ...rest }: MessageIconProps & { children: ReactNode }) {
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
      {children}
    </svg>
  )
}

export const InfoCircleIcon = (props: MessageIconProps) => (
  <Glyph size={12} {...props}><circle cx="10" cy="10" r="7" /><path strokeWidth={1.8} d="M10 9v4.5M10 6.6v.1" /></Glyph>
)
export const AlertTriangleIcon = (props: MessageIconProps) => (
  <Glyph {...props}><path d="M10 3.5 17 16H3z" /><path strokeWidth={1.7} d="M10 8.5v3.2M10 13.6v.1" /></Glyph>
)
export const AlertCircleIcon = (props: MessageIconProps) => (
  <Glyph {...props}><circle cx="10" cy="10" r="7.25" /><path strokeWidth={1.8} d="M10 6.2v4.6M10 13.4v.1" /></Glyph>
)
export const CheckIcon = (props: MessageIconProps) => (
  <Glyph size={11} strokeWidth={2.4} {...props}><path d="M5 10.5l3.2 3.2L15 6.8" /></Glyph>
)
export const CrossIcon = (props: MessageIconProps) => (
  <Glyph size={11} strokeWidth={2.4} {...props}><path d="M6 6l8 8M14 6l-8 8" /></Glyph>
)
