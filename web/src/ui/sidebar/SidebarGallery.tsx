import { useState, type ReactNode } from 'react'
import { useT } from '../../i18n/context'
import { Button } from '../Button'
import { Group } from '../gallery/Section'
import { Sidebar, SidebarBrand, SidebarSection } from './Sidebar'
import { SidebarCasesIcon, SidebarChatIcon, SidebarComposeIcon, SidebarSearchIcon } from './icons'
import { SidebarMenu, SidebarRowMenu, useChatMenuItems } from './SidebarMenu'
import { SidebarPerson } from './SidebarPerson'
import { SidebarRow } from './SidebarRow'
import { SidebarEmpty, SidebarSkeleton } from './SidebarState'
import './SidebarGallery.css'

const noop = () => {}

export function SidebarGallery() {
  const t = useT()
  return (
    <>
      <Group title={t('sidebar.sample.variants')}>
        <div className="gal-sidebar__variants">
          <Cell width={332} title={t('sidebar.sample.customer')} note={t('sidebar.sample.customerNote')}><Customer /></Cell>
          <Cell width={176} title={t('sidebar.sample.collapsed')} note={t('sidebar.sample.collapsedNote')}><Rail /></Cell>
          <Cell width={332} title={t('sidebar.sample.cases')} note={t('sidebar.sample.casesNote')}><WithCases /></Cell>
          <Cell width={292} title={t('sidebar.sample.operator')} note={t('sidebar.sample.operatorNote')}><Operator /></Cell>
        </div>
      </Group>

      <div className="gal-sidebar__states">
        <Group title={t('sidebar.sample.rowStates')}><RowStates /></Group>
        <Group title={t('sidebar.sample.rowMenu')}><MenuSample /></Group>
        <Group title={t('sidebar.sample.empty')}>
          <div className="gal-sidebar__card">
            <SidebarEmpty action={<Button size="sm">{t('sidebar.sample.newChat')}</Button>} />
          </div>
        </Group>
        <Group title={t('sidebar.sample.loading')}>
          <div className="gal-sidebar__card"><SidebarSkeleton /></div>
        </Group>
      </div>

      <Group title={t('sidebar.sample.live')}>
        <p className="gal__caption">{t('sidebar.sample.liveNote')}</p>
        <Live />
      </Group>
    </>
  )
}

function Cell({ title, note, width, children }: { title: string; note: string; width: number; children: ReactNode }) {
  return (
    <div className="gal-sidebar__cell" style={{ width }}>
      <div className="gal-sidebar__cell-head">
        <span className="gal__grid-label">{title}</span>
        <span className="gal__caption">{note}</span>
      </div>
      {children}
    </div>
  )
}

/** The window the sidebar sits in: 640px tall, clipped, with the soft shadow of Paper's frame. */
function Frame({ width, children }: { width: number; children: ReactNode }) {
  return <div className="gal-sidebar__frame" style={{ width }}>{children}</div>
}

function useSamples() {
  const t = useT()
  return {
    t,
    person: t('sidebar.sample.person'),
    detail: t('sidebar.sample.personDetail'),
    chat: (key: 'monthly' | 'charge' | 'cutoff' | 'balance' | 'limit' | 'pending' | 'trace') => t(`sidebar.sample.chat.${key}`),
  }
}

function Customer() {
  const { t, person, detail, chat } = useSamples()
  const items = useChatMenuItems()
  const menu = (name: string) => <SidebarRowMenu name={name} items={items} onSelect={noop} />
  return (
    <Frame width={332}>
      <Sidebar
        header={<SidebarBrand />}
        onCollapsedChange={noop}
        footer={<SidebarPerson name={person} detail={detail} onClick={noop} />}
      >
        <SidebarSection>
          <SidebarRow icon={<SidebarComposeIcon />} label={t('sidebar.sample.newChat')} shortcut="⌘N" />
          <SidebarRow icon={<SidebarSearchIcon />} label={t('sidebar.sample.search')} shortcut="⌘K" />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.today')}>
          <SidebarRow active label={chat('monthly')} meta={t('sidebar.sample.now')} menu={menu(chat('monthly'))} />
          <SidebarRow label={chat('charge')} status="working" menu={menu(chat('charge'))} />
          <SidebarRow label={chat('cutoff')} meta={t('sidebar.sample.hours')} menu={menu(chat('cutoff'))} />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.yesterday')}>
          <SidebarRow label={chat('balance')} status="unread" menu={menu(chat('balance'))} />
          <SidebarRow label={chat('limit')} meta={t('sidebar.sample.day')} menu={menu(chat('limit'))} />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.previous')}>
          <SidebarRow label={chat('pending')} meta={t('sidebar.sample.days4')} menu={menu(chat('pending'))} />
          <SidebarRow label={chat('trace')} meta={t('sidebar.sample.days6')} menu={menu(chat('trace'))} />
        </SidebarSection>
      </Sidebar>
    </Frame>
  )
}

function Rail() {
  const { t, person } = useSamples()
  return (
    <Frame width={176}>
      <Sidebar
        collapsed
        onCollapsedChange={noop}
        header={<SidebarBrand />}
        footer={<SidebarPerson name={person} onClick={noop} />}
      >
        <SidebarSection>
          <SidebarRow forceState="hover" icon={<SidebarComposeIcon />} label={t('sidebar.sample.newChat')} shortcut="⌘N" />
          <SidebarRow icon={<SidebarSearchIcon />} label={t('sidebar.sample.search')} shortcut="⌘K" />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.chats')}>
          <SidebarRow active icon={<SidebarChatIcon />} label={t('sidebar.sample.chats')} />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.casesTitle')}>
          <SidebarRow icon={<SidebarCasesIcon />} label={t('sidebar.sample.casesTitle')} status="unread" />
        </SidebarSection>
      </Sidebar>
    </Frame>
  )
}

function WithCases() {
  const { t, person, detail, chat } = useSamples()
  return (
    <Frame width={332}>
      <Sidebar header={<SidebarBrand />} footer={<SidebarPerson name={person} detail={detail} />}>
        <SidebarSection>
          <SidebarRow icon={<SidebarComposeIcon />} label={t('sidebar.sample.newChat')} />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.casesTitle')} meta={t('sidebar.sample.casesOpen')}>
          <SidebarRow active dot="accent" label={chat('charge')} description={t('sidebar.sample.case.person')} />
          <SidebarRow dot="success" label={t('sidebar.sample.chat.trace')} description={t('sidebar.sample.case.trace')} />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.chats')}>
          <SidebarRow label={chat('monthly')} meta={t('sidebar.sample.now')} />
          <SidebarRow label={chat('cutoff')} meta={t('sidebar.sample.hours')} />
          <SidebarRow label={chat('balance')} meta={t('sidebar.sample.day')} />
        </SidebarSection>
      </Sidebar>
    </Frame>
  )
}

const queues: readonly (readonly [string, number])[] = [
  ['fraud_ops', 3],
  ['priority_care', 1],
  ['complaints', 1],
  ['security_review', 1],
  ['compliance', 1],
  ['payments_ops', 2],
  ['account_payments_l2', 1],
]

function Operator() {
  const { t } = useSamples()
  return (
    <Frame width={292}>
      <Sidebar variant="operator" header={<SidebarBrand />} footer={<SidebarPerson name={t('sidebar.sample.operatorKey')} online />}>
        <SidebarSection>
          <SidebarRow active label={t('sidebar.sample.allOpen')} meta={10} />
          <SidebarRow label={t('sidebar.sample.mine')} meta={1} />
          <SidebarRow label={t('sidebar.sample.unassigned')} meta={8} />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.queues')}>
          {queues.map(([name, count]) => (
            <SidebarRow key={name} mono label={name} meta={count} />
          ))}
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.records')}>
          <SidebarRow label={t('sidebar.sample.auditLog')} />
          <SidebarRow label={t('sidebar.sample.traceLog')} />
        </SidebarSection>
      </Sidebar>
    </Frame>
  )
}

function RowStates() {
  const { t, chat } = useSamples()
  const items = useChatMenuItems()
  const name = chat('monthly')
  const hours = t('sidebar.sample.hours')
  const states = ['default', 'hover', 'selected', 'working', 'unread', 'renaming', 'focus'] as const
  return (
    <div className="gal-sidebar__row-states">
      <div className="gal-sidebar__state-labels">
        {states.map((state) => <span key={state} className="gal__caption">{t(`sidebar.sample.states.${state}`)}</span>)}
      </div>
      <Sidebar floating className="gal-sidebar__panel" header={null} label={t('sidebar.sample.rowStates')}>
        <SidebarSection>
          <SidebarRow label={name} meta={hours} />
          <SidebarRow forceState="hover" label={name} menu={<SidebarRowMenu name={name} items={items} onSelect={noop} />} />
          <SidebarRow active label={name} meta={hours} />
          <SidebarRow label={chat('charge')} status="working" />
          <SidebarRow label={chat('balance')} status="unread" />
          <SidebarRow renaming renameAutoFocus={false} label={name} />
          <SidebarRow forceState="focus" label={chat('cutoff')} meta={t('sidebar.sample.day')} />
        </SidebarSection>
      </Sidebar>
    </div>
  )
}

function MenuSample() {
  const t = useT()
  const items = useChatMenuItems()
  return (
    <div className="gal-sidebar__menu-sample">
      <SidebarMenu label={t('sidebar.sample.rowMenu')} items={items} onSelect={noop} autoFocus={false} forceActive={0} />
    </div>
  )
}

type LiveChat = { id: string; name: string; meta: string }

/** A sidebar that works: collapse, choose a row, open its menu with the keyboard, rename, delete. */
function Live() {
  const { t, person, detail, chat } = useSamples()
  const items = useChatMenuItems()
  const [collapsed, setCollapsed] = useState(false)
  const [active, setActive] = useState('a')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [chats, setChats] = useState<LiveChat[]>(() => [
    { id: 'a', name: chat('monthly'), meta: t('sidebar.sample.now') },
    { id: 'b', name: chat('cutoff'), meta: t('sidebar.sample.hours') },
    { id: 'c', name: chat('limit'), meta: t('sidebar.sample.day') },
    { id: 'd', name: chat('pending'), meta: t('sidebar.sample.days4') },
  ])

  function choose(id: string, action: string) {
    if (action === 'rename') setRenaming(id)
    else if (action === 'delete' || action === 'archive') setChats((all) => all.filter((item) => item.id !== id))
  }

  return (
    <div className="gal-sidebar__frame gal-sidebar__frame--live">
      <Sidebar
        collapsed={collapsed}
        onCollapsedChange={setCollapsed}
        header={<SidebarBrand />}
        footer={<SidebarPerson name={person} detail={detail} onClick={noop} />}
      >
        <SidebarSection>
          <SidebarRow icon={<SidebarComposeIcon />} label={t('sidebar.sample.newChat')} shortcut="⌘N" />
          <SidebarRow icon={<SidebarSearchIcon />} label={t('sidebar.sample.search')} shortcut="⌘K" />
        </SidebarSection>
        <SidebarSection title={t('sidebar.sample.chats')}>
          {chats.length === 0 && !collapsed ? (
            <li><SidebarEmpty action={<Button size="sm" onClick={() => setChats([{ id: 'n', name: t('sidebar.sample.newChat'), meta: t('sidebar.sample.now') }])}>{t('sidebar.sample.newChat')}</Button>} /></li>
          ) : (
            chats.map((item) => (
              <SidebarRow
                key={item.id}
                icon={collapsed ? <SidebarChatIcon /> : undefined}
                label={item.name}
                meta={item.meta}
                active={active === item.id}
                onClick={() => setActive(item.id)}
                renaming={renaming === item.id}
                onRename={(name) => {
                  setChats((all) => all.map((row) => (row.id === item.id ? { ...row, name } : row)))
                  setRenaming(null)
                }}
                onRenameCancel={() => setRenaming(null)}
                menu={<SidebarRowMenu name={item.name} items={items} onSelect={(action) => choose(item.id, action)} />}
              />
            ))
          )}
        </SidebarSection>
      </Sidebar>
    </div>
  )
}
