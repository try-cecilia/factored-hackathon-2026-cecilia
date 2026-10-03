import { login } from './dict/pt/auth.ts'
import { cases } from './dict/pt/cases.ts'
import { chat } from './dict/pt/chat.ts'
import { conversation } from './dict/pt/conversation.ts'
import { demo } from './dict/pt/demo.ts'
import { gallery } from './dict/pt/gallery.ts'
import { landing } from './dict/pt/landing.ts'
import { common } from './dict/pt/common.ts'
import { loaders } from './dict/pt/loaders.ts'
import { monitor } from './dict/pt/monitor.ts'
import { operator } from './dict/pt/operator.ts'
import { shell } from './dict/pt/shell.ts'
import { sidebar } from './dict/pt/sidebar.ts'
import { table } from './dict/pt/table.ts'
import type { Messages } from './types.ts'

/** Brazilian Portuguese. It must have exactly the keys of `es`: typecheck fails if one is missing or extra. */
export const pt = { common, shell, landing, login, gallery, loaders, sidebar, table, chat, cases, conversation, demo, operator, monitor }
