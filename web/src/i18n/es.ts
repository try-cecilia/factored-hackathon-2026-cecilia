import { home, login } from './dict/es/auth.ts'
import { cases } from './dict/es/cases.ts'
import { chat } from './dict/es/chat.ts'
import { conversation } from './dict/es/conversation.ts'
import { demo } from './dict/es/demo.ts'
import { gallery } from './dict/es/gallery.ts'
import { common } from './dict/es/common.ts'
import { loaders } from './dict/es/loaders.ts'
import { shell } from './dict/es/shell.ts'
import { sidebar } from './dict/es/sidebar.ts'
import { table } from './dict/es/table.ts'

/** Source language and definition of the keys. UI copy in neutral Spanish for AR, MX and CO: no voseo, no regionalisms. */
export const es = { common, shell, home, login, gallery, loaders, sidebar, table, chat, cases, conversation, demo }
