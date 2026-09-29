import { Link, useNavigate, useRouter } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Session } from '../server/auth.functions'
import { sendMessage } from '../server/chat.functions'
import { Composer, type ComposerHandle } from './Composer'
import { DemoPanel } from './DemoPanel'
import { AssistantMessage, ErrorMessage, Thinking, UserMessage, type Entry } from './Message'
import { ClockIcon, LockIcon, OfflineIcon } from './icons'
import type { DemoScenario, Reply } from './types'

const SUGGESTIONS = [
  '¿Cuál es mi saldo?',
  'Mis últimos movimientos',
  '¿Estoy al día con mi tarjeta de crédito?',
  '¿A cuánto está el dólar?',
  'Hice una transferencia que todavía no llega',
]
const WARN_SECONDS = 120

type WithoutStamp<T> = T extends unknown ? Omit<T, 'id' | 'at'> : never
type NewEntry = WithoutStamp<Entry>

function useSessionClock(session: Session) {
  const [left, setLeft] = useState(session.expires_in)
  useEffect(() => {
    const deadline = Date.now() + session.expires_in * 1000
    const tick = () => setLeft(Math.max(0, Math.round((deadline - Date.now()) / 1000)))
    tick()
    const timer = setInterval(tick, 5_000)
    return () => clearInterval(timer)
  }, [session.session_ref, session.expires_in])
  return left
}

function useOnline() {
  const [online, setOnline] = useState(true)
  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    update()
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])
  return online
}

export function ChatView({ session, scenarios }: { session: Session; scenarios: DemoScenario[] | null }) {
  const navigate = useNavigate()
  const router = useRouter()
  const [entries, setEntries] = useState<Entry[]>([])
  const [pending, setPending] = useState(false)
  const nextId = useRef(1)
  const pendingRef = useRef(false)
  const composer = useRef<ComposerHandle>(null)
  const end = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const left = useSessionClock(session)
  const online = useOnline()
  const expired = left === 0

  // A different session (a demo scenario, or signing in again) starts a different conversation.
  useEffect(() => {
    setEntries([])
    setPending(false)
    pendingRef.current = false
  }, [session.session_ref])

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    end.current?.scrollIntoView({ block: 'end', behavior: reduce ? 'auto' : 'smooth' })
  }, [entries, pending])

  // A case card or a "why" grows after its message arrives: stay at the bottom if that is where the reader was.
  useEffect(() => {
    const inner = content.current
    const log = logRef.current
    if (!inner || !log) return
    let height = inner.offsetHeight
    const observer = new ResizeObserver(() => {
      const grew = inner.offsetHeight > height
      height = inner.offsetHeight
      if (grew && log.scrollHeight - log.scrollTop - log.clientHeight < 160) log.scrollTop = log.scrollHeight
    })
    observer.observe(inner)
    return () => observer.disconnect()
  }, [])

  const goToLogin = useCallback(() => {
    void navigate({ to: '/login', search: { redirect: '/chat', motivo: 'expired' }, replace: true })
  }, [navigate])

  const push = useCallback((entry: NewEntry) => {
    setEntries((all) => [...all, { ...entry, id: nextId.current++, at: new Date() } as Entry])
  }, [])

  // One turn at a time: the ref answers a second click before React has re-rendered.
  const deliver = useCallback(async (text: string): Promise<Reply | null> => {
    if (pendingRef.current) return null
    pendingRef.current = true
    setPending(true)
    try {
      const result = await sendMessage({ data: { message: text } })
      if (result.ok) {
        push({ role: 'assistant', reply: result.reply })
        return result.reply
      }
      if (result.failure === 'session_expired') goToLogin()
      else push({ role: 'error', failure: result.failure, text })
    } catch {
      push({ role: 'error', failure: 'unexpected', text })
    } finally {
      pendingRef.current = false
      setPending(false)
      composer.current?.focus()
    }
    return null
  }, [push, goToLogin])

  const send = useCallback((text: string) => {
    if (pendingRef.current) return Promise.resolve(null)
    push({ role: 'user', text })
    return deliver(text)
  }, [push, deliver])

  const retry = useCallback((entry: Extract<Entry, { role: 'error' }>) => {
    if (pendingRef.current) return
    setEntries((all) => all.filter((e) => e.id !== entry.id))
    void deliver(entry.text)
  }, [deliver])

  const last = entries.at(-1)
  const minutes = Math.max(1, Math.ceil(left / 60))
  const escalations = entries.filter((e) => e.role === 'assistant' && e.reply.disposition === 'ESCALATE').length

  return (
    <div className="chat">
      <header className="chat-head">
        <h1>Asistente de cuenta</h1>
        <span className="trust"><LockIcon />Nada se hace sin tu confirmación</span>
      </header>
      <div className="chat-main">
        <div className="chat-col">
          <div
            ref={logRef}
            className="log"
            role="log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label="Conversación con Cecilia"
            tabIndex={0}
          >
            <div ref={content} className="log-inner">
              {entries.length === 0 && !pending && (
                <div className="empty">
                  <img src="/cecilia-avatar.png" alt="" width={56} height={56} />
                  <h2>Hola, soy Cecilia.</h2>
                  <p>Te ayudo con saldos, movimientos, estado de pagos y tipo de cambio. Escribime en español o en portugués.</p>
                </div>
              )}
              {entries.map((entry) => {
                const active = entry === last && !pending
                if (entry.role === 'user') return <UserMessage key={entry.id} entry={entry} />
                if (entry.role === 'error') return <ErrorMessage key={entry.id} entry={entry} active={active && online} onRetry={retry} />
                return (
                  <AssistantMessage
                    key={entry.id}
                    entry={entry}
                    active={active && !expired && online}
                    busy={pending}
                    onAnswer={(text) => void send(text)}
                    onSessionExpired={goToLogin}
                  />
                )
              })}
              {pending && <Thinking />}
            </div>
            <div ref={end} />
          </div>
          <div className="notices">
            {!online && (
              <div className="callout callout-danger" role="status">
                <OfflineIcon />
                <span>Estás sin conexión. Vas a poder enviar mensajes cuando vuelva.</span>
              </div>
            )}
            {expired ? (
              <div className="callout callout-sun" role="alert">
                <ClockIcon />
                <span>Tu sesión venció.</span>
                <Link to="/login" search={{ redirect: '/chat' }} className="callout-action">Ingresar de nuevo</Link>
              </div>
            ) : (
              left <= WARN_SECONDS && (
                <div className="callout callout-neutral" role="status">
                  <ClockIcon />
                  <span>Tu sesión termina en {minutes} {minutes === 1 ? 'minuto' : 'minutos'}.</span>
                </div>
              )
            )}
          </div>
          <Composer
            key={session.session_ref}
            ref={composer}
            disabled={expired || !online}
            pending={pending}
            hint={expired ? 'Tu sesión venció. Ingresá de nuevo para seguir.' : 'Sin conexión'}
            suggestions={entries.length === 0 ? SUGGESTIONS : []}
            onSend={(text) => void send(text)}
          />
        </div>
        {scenarios && (
          <DemoPanel
            scenarios={scenarios}
            sessionRef={session.session_ref}
            pending={pending}
            escalations={escalations}
            send={send}
            onSessionChanged={() => router.invalidate()}
          />
        )}
      </div>
    </div>
  )
}
