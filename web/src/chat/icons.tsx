// Icons drawn in the Paper file (20x20 grid, 1.6 stroke). Decorative: always aria-hidden.
export const LockIcon = ({ size = 12 }: { size?: number }) => (
  <svg viewBox="0 0 20 20" width={size} height={size} aria-hidden="true" focusable="false" className="icon">
    <rect x="4.5" y="9" width="11" height="8" rx="2" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M7 9V6.5a3 3 0 0 1 6 0V9" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
