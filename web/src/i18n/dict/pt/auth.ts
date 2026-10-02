import type { Like } from '../../types.ts'
import type { home as esHome, login as esLogin } from '../es/auth.ts'

export const home: Like<typeof esHome> = {
  titleLine1: 'Conheça a Cecilia,',
  titleLine2: 'sua assistente bancária.',
  lead: 'Consulte saldos, movimentações e pagamentos em linguagem simples. Se for preciso uma pessoa, a Cecilia passa o seu caso completo.',
  signIn: 'Entrar',
}

export const login: Like<typeof esLogin> = {
  pageTitle: 'Entrar · Cecilai',
  title: 'Olá de novo.',
  lead: 'Com o seu número de cliente e o seu PIN de 6 dígitos.',
  expired: 'Sua sessão expirou. Ao entrar de novo, a conversa começa do zero.',
  signOutUnconfirmed: 'Não foi possível confirmar que a sessão foi encerrada no servidor. Você já saiu deste navegador, mas o acesso pode continuar válido no servidor até a sessão expirar.',
  customerId: 'Número de cliente',
  pin: 'PIN',
  submit: 'Entrar',
  submitting: 'Entrando…',
  demoBadge: 'Demo',
  demoAccounts: 'Contas de teste',
  errors: {
    badCredentials: 'Número de cliente ou PIN incorretos.',
    tooManyAttempts: 'Muitas tentativas. Tentar novamente em alguns minutos.',
    unavailable: 'O serviço não está disponível neste momento.',
    customerIdRequired: 'Falta o número de cliente.',
    customerIdShort: 'O número de cliente tem pelo menos 3 caracteres.',
    pinRequired: 'Falta o PIN de 6 dígitos.',
    pinShort: 'O PIN tem 6 dígitos.',
    sessionNotSaved: 'Seu navegador não guardou a sessão. Verifique se ele aceita cookies deste site e tente de novo. Fora do localhost, o app deve ser aberto por https.',
  },
}
