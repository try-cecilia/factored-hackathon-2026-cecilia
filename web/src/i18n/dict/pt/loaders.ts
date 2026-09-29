import type { Like } from '../../types.ts'
import type { loaders as es } from '../es/loaders.ts'

export const loaders: Like<typeof es> = {
  loading: 'Carregando…',
  thinking: 'A Cecilia está pensando',
  status: {
    pending: 'pendente',
    active: 'em andamento',
    done: 'concluído',
    failed: 'com erro',
  },
  steps: {
    label: 'Verificações da Cecilia',
  },
  progress: {
    stepsLabel: 'Etapas do processo',
  },
  delivery: {
    sending: 'Enviando',
    sent: 'Enviado',
    sentAt: 'Enviado · {time}',
    failed: 'Não enviado',
    retry: 'Tentar novamente',
    uncertain: 'Sem confirmação',
    processed: 'Recebido',
    reload: 'Carregar a conversa',
  },
  toast: {
    close: 'Fechar',
    region: 'Notificações',
  },
  sample: {
    spinner: {
      title: '1 · Spinner',
      lead: 'Um anel, quatro tamanhos, três tons. O determinado usa o mesmo anel.',
      brand: 'Marca',
      onDark: 'Sobre escuro',
      done: 'Concluído',
    },
    thinking: {
      title: '2 · Pontos de espera',
      lead: 'Do envio até a chegada da primeira linha. Três quadros do pulso.',
      frame: 'Quadro {n}',
    },
    steps: {
      title: '3 · Etapas de verificação',
      lead: 'Mostra as consultas reais, em ordem. As marcas aparecem conforme cada uma é verificada.',
      accounts: 'Contas verificadas',
      reading: 'Lendo os movimentos de agosto',
      preparing: 'Preparando sua resposta',
      failedLabel: 'Com erro',
      failed: 'Não foi possível ler o detalhe',
    },
    skeleton: {
      title: '4 · Esqueletos',
      lead: 'Mensagem, cartão de resumo. Dois tons se alternam para parecer carregamento, não vazio.',
    },
    progress: {
      title: '5 · Progresso',
      lead: 'Determinado, indeterminado e por etapas para fluxos de várias partes.',
      opening: 'Abrindo o acompanhamento',
      loading: 'Carregando movimentos',
      verify: 'Verificar',
      confirm: 'Confirmar',
      done: 'Concluído',
    },
    delivery: {
      title: '6 · Entrega da mensagem',
      lead: 'O balão do cliente traz o seu estado logo abaixo.',
      message: 'Mostre meus últimos cinco movimentos',
      time: '08:52',
      uncertainDetail: 'Não consegui confirmar se o serviço recebeu sua mensagem. Tentar novamente é seguro: se já recebeu, ela não se repete.',
      processedDetail: 'O serviço já recebeu esta mensagem. Carregar a conversa mostra a resposta.',
    },
    page: {
      title: '7 · Página e aviso',
      lead: 'Espera do login e um aviso de atualização que nunca bloqueia a tela.',
      signingIn: 'Entrando com segurança',
      updating: 'Atualizando movimentos',
      updated: 'Movimentos atualizados',
      failed: 'Não foi possível atualizar',
      retryAction: 'Tentar novamente',
    },
  },
}
