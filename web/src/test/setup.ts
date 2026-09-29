import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { dropConflicts } from '../routes/-operator/conflicts'

afterEach(() => {
  cleanup()
  dropConflicts()
})
