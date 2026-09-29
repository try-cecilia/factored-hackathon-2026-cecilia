import { home, login } from './dict/pt/auth.ts'
import { chat } from './dict/pt/chat.ts'
import { gallery } from './dict/pt/gallery.ts'
import { common } from './dict/pt/common.ts'
import { loaders } from './dict/pt/loaders.ts'
import { monitor } from './dict/pt/monitor.ts'
import { operator } from './dict/pt/operator.ts'
import { shell } from './dict/pt/shell.ts'
import { sidebar } from './dict/pt/sidebar.ts'
import { table } from './dict/pt/table.ts'
import type { Messages } from './types.ts'

/** Brazilian Portuguese. It must have exactly the keys of `es`: typecheck fails if one is missing or extra. */
export const pt: Messages = { common, shell, home, login, gallery, loaders, sidebar, table, chat, operator, monitor }
