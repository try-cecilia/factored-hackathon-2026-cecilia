import { home, login } from './dict/es/auth.ts'
import { chat } from './dict/es/chat.ts'
import { gallery } from './dict/es/gallery.ts'
import { common } from './dict/es/common.ts'
import { loaders } from './dict/es/loaders.ts'
import { monitor } from './dict/es/monitor.ts'
import { operator } from './dict/es/operator.ts'
import { shell } from './dict/es/shell.ts'
import { sidebar } from './dict/es/sidebar.ts'
import { table } from './dict/es/table.ts'

/** Source language and definition of the keys. UI copy in neutral Spanish for AR, MX and CO: no voseo, no regionalisms. */
export const es = { common, shell, home, login, gallery, loaders, sidebar, table, chat, operator, monitor }
