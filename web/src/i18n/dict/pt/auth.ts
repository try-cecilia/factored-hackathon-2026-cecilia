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
  },
}
