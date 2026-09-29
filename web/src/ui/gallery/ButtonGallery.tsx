import { useT } from '../../i18n/context'
import { Button, IconButton, type ButtonVariant } from '../Button'
import { ArrowRightIcon, ArrowUpIcon, CopyIcon, MenuIcon, PlusIcon, TrashIcon } from '../icons'
import { Group } from './Section'

const variants: ButtonVariant[] = ['primary', 'destructive', 'ghost', 'outline']
const states = ['default', 'hover', 'pressed', 'focus', 'disabled', 'loading'] as const

export function ButtonGallery() {
  const t = useT()
  const label = (variant: ButtonVariant, loading = false) =>
    t(`gallery.buttons.labels.${variant}${loading ? 'Loading' : ''}` as const)

  return (
    <>
      <Group title={t('gallery.buttons.variants')}>
        <div className="gal__grid">
          <span />
          {states.map((state) => (
            <span key={state} className="gal__grid-head">{t(`gallery.buttons.states.${state}`)}</span>
          ))}
          {variants.map((variant) => (
            <Row key={variant} variant={variant} name={t(`gallery.buttons.variantNames.${variant}`)} label={label(variant)} loadingLabel={label(variant, true)} />
          ))}
        </div>
      </Group>

      <Group title={t('gallery.buttons.sizes')}>
        <div className="gal__row" style={{ alignItems: 'end', gap: 32 }}>
          <Cell caption={t('gallery.buttons.sizeLargeUse')}><Button size="lg">{t('gallery.buttons.sizeLarge')}</Button></Cell>
          <Cell caption={t('gallery.buttons.sizeMediumUse')}><Button size="md">{t('gallery.buttons.sizeMedium')}</Button></Cell>
          <Cell caption={t('gallery.buttons.sizeSmallUse')}><Button size="sm">{t('gallery.buttons.sizeSmall')}</Button></Cell>
          <Cell caption={t('gallery.buttons.sizeCompactUse')}><Button size="xs">{t('gallery.buttons.sizeCompact')}</Button></Cell>
        </div>
      </Group>

      <Group title={t('gallery.buttons.withIcons')}>
        <div className="gal__row" style={{ gap: 32 }}>
          <Cell caption={t('gallery.buttons.leadingIcon')}><Button leadingIcon={<PlusIcon />}>{t('gallery.buttons.newChat')}</Button></Cell>
          <Cell caption={t('gallery.buttons.trailingIcon')}><Button variant="ghost" tinted trailingIcon={<ArrowRightIcon />}>{t('gallery.buttons.next')}</Button></Cell>
          <Cell caption={t('gallery.buttons.iconPrimary')}><IconButton label={t('gallery.buttons.send')} icon={<ArrowUpIcon />} /></Cell>
          <Cell caption={t('gallery.buttons.iconGhost')}><IconButton variant="ghost" forceState="hover" label={t('gallery.buttons.menu')} icon={<MenuIcon />} /></Cell>
          <Cell caption={t('gallery.buttons.iconOutline')}><IconButton variant="outline" label={t('gallery.buttons.copy')} icon={<CopyIcon />} /></Cell>
          <Cell caption={t('gallery.buttons.iconDestructive')}><IconButton variant="destructive" label={t('gallery.buttons.delete')} icon={<TrashIcon />} /></Cell>
          <Cell caption={t('gallery.buttons.withCount')}><Button variant="ghost" forceState="hover" count={2}>{t('gallery.buttons.cases')}</Button></Cell>
        </div>
      </Group>

      <Group title={t('gallery.buttons.inContext')}>
        <div className="gal__row" style={{ alignItems: 'start', gap: 64 }}>
          <Cell caption={t('gallery.buttons.groupConfirm')}>
            <div className="gal__row" style={{ gap: 8 }}>
              <Button>{t('gallery.buttons.groupConfirmPrimary')}</Button>
              <Button variant="ghost">{t('gallery.buttons.groupConfirmGhost')}</Button>
            </div>
          </Cell>
          <Cell caption={t('gallery.buttons.groupDestructive')}>
            <div className="gal__row" style={{ gap: 8 }}>
              <Button variant="destructive">{t('gallery.buttons.groupDestructivePrimary')}</Button>
              <Button variant="ghost" tinted>{t('gallery.buttons.groupDestructiveKeep')}</Button>
            </div>
          </Cell>
          <Cell caption={t('gallery.buttons.groupDesk')}>
            <div className="gal__row" style={{ gap: 8 }}>
              <Button size="xs">{t('gallery.buttons.claim')}</Button>
              <Button size="xs" variant="outline">{t('gallery.buttons.reject')}</Button>
              <Button size="xs" variant="ghost" muted>{t('gallery.buttons.release')}</Button>
            </div>
          </Cell>
        </div>
      </Group>
    </>
  )
}

function Cell({ caption, children }: { caption: string; children: React.ReactNode }) {
  return (
    <div className="gal__cell">
      {children}
      <span className="gal__caption">{caption}</span>
    </div>
  )
}

function Row({ variant, name, label, loadingLabel }: { variant: ButtonVariant; name: string; label: string; loadingLabel: string }) {
  return (
    <>
      <span className="gal__grid-label">{name}</span>
      <div><Button variant={variant}>{label}</Button></div>
      <div><Button variant={variant} forceState="hover">{label}</Button></div>
      <div><Button variant={variant} forceState="pressed">{label}</Button></div>
      <div><Button variant={variant} forceState="focus">{label}</Button></div>
      <div><Button variant={variant} disabled>{label}</Button></div>
      <div><Button variant={variant} loading>{loadingLabel}</Button></div>
    </>
  )
}
