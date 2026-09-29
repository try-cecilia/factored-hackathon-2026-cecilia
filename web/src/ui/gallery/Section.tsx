import type { ReactNode } from 'react'

/** A titled block of the gallery. The `id` is the anchor of the top navigation. */
export function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="gal__section" id={id} aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{title}</h2>
      {children}
    </section>
  )
}

export function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="gal__group">
      <h3>{title}</h3>
      {children}
    </div>
  )
}
