import type { Like } from '../../types.ts'
import type { cases as es } from '../es/cases.ts'

export const cases: Like<typeof es> = {
  title: 'Casos',
  openOne: '1 aberto',
  openMany: '{n} abertos',
  empty: {
    title: 'Sem casos por enquanto',
    description: 'Se a Cecilia passar uma consulta a uma pessoa, o caso aparece aqui com o seu status.',
  },
  loading: 'Consultando o status…',
  unavailable: 'Não foi possível consultar o status',
  update: 'Atualizar o status',
  row: '{title}, {status}, caso {id}',
  status: {
    open: 'Recebido',
    claimed: 'Em análise',
    approved: 'Aprovado',
    rejected: 'Recusado',
    handed_back: 'Devolvido à Cecilia',
    stale: 'Sem alterações necessárias',
    unknown: 'Em andamento',
  },
  category: {
    fraud: 'Possível fraude',
    theft: 'Roubo ou clonagem de cartão',
    account_takeover: 'Acesso não autorizado',
    safety: 'Atendimento prioritário',
    legal_or_regulator: 'Reclamação ou consulta jurídica',
    classifier_escalation: 'Movimentação não reconhecida',
    compliance_hold: 'Revisão da sua conta',
    security: 'Revisão de segurança',
    trace_unmatched: 'Pagamento ou transferência que não chegou',
    trace_unverified: 'Rastreamento de uma movimentação',
    trace_review: 'Rastreamento de uma movimentação',
    pending: 'Consulta pendente de revisão',
    other: 'Caso passado a uma pessoa',
  },
}
