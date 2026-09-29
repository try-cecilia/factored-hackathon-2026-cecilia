import type { Like } from '../../types.ts'
import type { shell as es } from '../es/shell.ts'

export const shell: Like<typeof es> = {
  pageTitle: {
    chat: 'Chat · Cecilai',
  },
  mainNav: 'Principal',
  nav: {
    chat: 'Chat',
  },
  customer: 'Cliente {id}',
  signOut: 'Sair',
  signingOut: 'Saindo…',
  signOutFailed: 'Não foi possível encerrar a sessão. Tentar novamente.',
  unavailable: {
    title: 'Serviço indisponível.',
    body: 'Não conseguimos conectar ao serviço neste momento. Tentar novamente em alguns minutos.',
  },
}
