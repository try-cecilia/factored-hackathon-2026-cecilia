import type { Like } from '../../types.ts'
import type { shell as es } from '../es/shell.ts'

export const shell: Like<typeof es> = {
  pageTitle: {
    chat: 'Chat · Cecilai',
  },
  mainNav: 'Principal',
  nav: {
    chat: 'Chat',
    conversation: 'Conversa',
  },
  customer: 'Cliente {id}',
  signOut: 'Sair',
  signingOut: 'Saindo…',
  signOutFailed: 'Não foi possível encerrar a sessão.',
  menu: {
    open: 'Abrir o menu',
    close: 'Fechar o menu',
    scrim: 'Fechar o menu',
  },
  demo: {
    toggle: 'Demo',
    show: 'Mostrar o painel de demo',
    hide: 'Ocultar o painel de demo',
  },
  unavailable: {
    title: 'Serviço indisponível.',
    body: 'Não conseguimos conectar ao serviço neste momento. Tentar novamente em alguns minutos.',
  },
}
