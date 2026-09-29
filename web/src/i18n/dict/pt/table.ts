import type { Like } from '../../types.ts'
import type { table as es } from '../es/table.ts'

export const table: Like<typeof es> = {}
