// Public surface of the sidebar components: one export line per component. The gallery is not exported from here, nor what only
// the gallery draws (SidebarMenu): the gallery imports it from its file, so the app's bundle does not carry it.
export { Sidebar, SidebarBrand, SidebarSection, type SidebarProps, type SidebarSectionProps } from './Sidebar'
export type { SidebarVariant } from './SidebarContext'
export { SidebarRow, type SidebarDotTone, type SidebarRowProps, type SidebarRowStatus } from './SidebarRow'
export { SidebarPerson, type SidebarPersonProps } from './SidebarPerson'
export { SidebarEmpty, SidebarSkeleton, type SidebarEmptyProps } from './SidebarState'
export * from './icons'
