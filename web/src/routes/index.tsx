import { createFileRoute } from '@tanstack/react-router'
import { headTitle } from '../i18n/head'
import { Landing } from '../landing/Landing'

export const Route = createFileRoute('/')({
  head: ({ matches }) => headTitle(matches, 'landing.pageTitle'),
  component: Landing,
})
