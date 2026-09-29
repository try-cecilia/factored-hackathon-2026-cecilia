import type { es } from './es.ts'

/** Same keys as T with every string widened, so a translation can differ from the Spanish source text. */
export type Like<T> = { [K in keyof T]: T[K] extends string ? string : Like<T[K]> }

/** The shape of a dictionary. `es` defines it; `pt` is typed against it, so a missing or extra key fails typecheck. */
export type Messages = Like<typeof es>
