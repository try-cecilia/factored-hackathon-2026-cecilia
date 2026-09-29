import { useNavigate } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useT } from '../i18n/context'
import type { Session } from '../server/auth.functions'
import { Button, SystemNote } from '../ui'
import { ChatLog } from './ChatLog'
import { Composer, type ComposerHandle } from './Composer'
import { useConversation } from './ConversationProvider'
import { sessionNotice } from './conversation'
import { useShell } from '../shell/ShellContext'
import './chat.css'

/**
 * What the session's countdown shows (`sessionNotice`): no notice, the minutes of the notice, or over. It ticks every five
 * seconds but holds that, not the seconds, so the page renders again only when what it shows changes.
 */
function useSessionNotice(session: Session) {
  const [notice, setNotice] = useState(() => sessionNotice(session.expires_in))
  useEffect(() => {
    const deadline = Date.now() + session.expires_in * 1000
    const tick = () => setNotice(sessionNotice(Math.round((deadline - Date.now()) / 1000)))
    tick()
    const timer = setInterval(tick, 5_000)
    return () => clearInterval(timer)
  }, [session.session_ref, session.expires_in])
  return notice
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

export function ChatView({ session }: { session: Session }) {
  const t = useT()
  const navigate = useNavigate()
  const { entries, cases, sending, ended, historyFailed, send, retry, reload } = useConversation()
  const { showCase } = useShell()
  const composer = useRef<ComposerHandle>(null)
  const end = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const notice = useSessionNotice(session)
  const online = useOnline()
  const over = ended || notice === 0
  const live = online && !over
  const [reloading, setReloading] = useState(false)

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    end.current?.scrollIntoView({ block: 'end', behavior: reduce ? 'auto' : 'smooth' })
  }, [entries, sending, over])

  // A card or a "why" grows after its message arrives: stay at the bottom if that is where the reader was.
  useEffect(() => {
    const inner = content.current
    const box = scroller.current
    if (!inner || !box) return
    let height = inner.offsetHeight
    const observer = new ResizeObserver(() => {
      const grew = inner.offsetHeight > height
      height = inner.offsetHeight
      if (grew && box.scrollHeight - box.scrollTop - box.clientHeight < 160) box.scrollTop = box.scrollHeight
    })
    observer.observe(inner)
    return () => observer.disconnect()
  }, [])

  // After a turn ends the focus goes back to the composer; on load it stays where the page put it (the skip link first).
  const wasSending = useRef(false)
  useEffect(() => {
    if (wasSending.current && !sending) composer.current?.focus()
    wasSending.current = sending
  }, [sending])

  const signIn = useCallback(() => {
    void navigate({ to: '/login', search: { redirect: '/chat', motivo: 'expired' }, replace: true })
  }, [navigate])

  const reloadHistory = useCallback(async () => {
    setReloading(true)
    await reload()
    setReloading(false)
  }, [reload])

  // Stable, so the memoized log renders only when the conversation or its state changes.
  const sendText = useCallback((text: string) => void send(text), [send])
  const reloadLog = useCallback(() => void reloadHistory(), [reloadHistory])

  const empty = entries.length === 0 && !sending

  return (
    <div className="chat">
      <div ref={scroller} className="chat__scroll" tabIndex={0} role="region" aria-label={t('conversation.title')}>
        <div ref={content} className="chat__inner">
          {historyFailed && (
            <div className="chat__history" role="status">
              <span>{t('conversation.history.failed')}</span>
              <Button variant="ghost" size="sm" tinted loading={reloading} onClick={() => void reloadHistory()}>{t('conversation.history.retry')}</Button>
            </div>
          )}
          {empty && (
            <div className="chat__empty">
              <img src="/cecilia-avatar.png" alt="" width={112} height={112} />
              <h2>{t('conversation.empty.title')}</h2>
              <p>{t('conversation.empty.body')}</p>
            </div>
          )}
          <ChatLog
            entries={entries}
            cases={cases}
            sending={sending}
            live={live}
            ended={over}
            onSend={sendText}
            onRetry={retry}
            onReload={reloadLog}
            onViewCase={showCase}
            onSignIn={signIn}
          />
        </div>
        <div ref={end} />
      </div>
      <div className="chat__foot">
        <div className="chat__notices" role="status">
          {!online && <SystemNote tone="neutral">{t('conversation.session.offline')}</SystemNote>}
          {over ? (
            <SystemNote tone="neutral">{t('conversation.session.expired')}</SystemNote>
          ) : (
            notice !== null && (
              <SystemNote tone="neutral">{t(notice === 1 ? 'conversation.session.endsOne' : 'conversation.session.endsMany', { n: notice })}</SystemNote>
            )
          )}
        </div>
        <Composer
          key={session.session_ref}
          ref={composer}
          disabled={over || !online}
          pending={sending}
          hint={over ? t('conversation.composer.sessionEnded') : t('conversation.composer.offline')}
          showSuggestions={entries.length === 0}
          onSend={sendText}
        />
      </div>
    </div>
  )
}

