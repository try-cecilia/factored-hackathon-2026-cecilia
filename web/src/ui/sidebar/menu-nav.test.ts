import assert from 'node:assert/strict'
import { test } from 'node:test'
import { matchTypeahead, moveFocus, nextTypeahead } from './menu-nav.ts'

const all = [true, true, true, true]

test('arrows move one item and wrap at both ends', () => {
  assert.equal(moveFocus(all, 0, 'ArrowDown'), 1)
  assert.equal(moveFocus(all, 3, 'ArrowDown'), 0)
  assert.equal(moveFocus(all, 0, 'ArrowUp'), 3)
  assert.equal(moveFocus(all, 2, 'ArrowUp'), 1)
})

test('Home and End go to the first and last enabled item', () => {
  const enabled = [false, true, true, false]
  assert.equal(moveFocus(enabled, 2, 'Home'), 1)
  assert.equal(moveFocus(enabled, 1, 'End'), 2)
})

test('disabled items are skipped, also across the wrap', () => {
  const enabled = [true, false, false, true]
  assert.equal(moveFocus(enabled, 0, 'ArrowDown'), 3)
  assert.equal(moveFocus(enabled, 3, 'ArrowDown'), 0)
  assert.equal(moveFocus(enabled, 0, 'ArrowUp'), 3)
})

test('with no focus yet, ArrowDown picks the first item and ArrowUp the last', () => {
  assert.equal(moveFocus(all, -1, 'ArrowDown'), 0)
  assert.equal(moveFocus(all, -1, 'ArrowUp'), 3)
  assert.equal(moveFocus([false, true, true, false], -1, 'ArrowDown'), 1)
  assert.equal(moveFocus([false, true, true, false], -1, 'ArrowUp'), 2)
})

test('a menu with nothing enabled gives no target', () => {
  assert.equal(moveFocus([false, false], 0, 'ArrowDown'), -1)
  assert.equal(moveFocus([], -1, 'Home'), -1)
  assert.equal(moveFocus([true], 0, 'ArrowDown'), 0)
})

const labels = ['Renombrar', 'Fijar', 'Archivar', 'Eliminar']

test('type-ahead finds the next label that starts with the letters, ignoring case and accents', () => {
  assert.equal(matchTypeahead(labels, all, -1, 'a'), 2)
  assert.equal(matchTypeahead(labels, all, 0, 'E'), 3)
  assert.equal(matchTypeahead(['Álbum', 'Bolsa'], [true, true], -1, 'al'), 0)
  assert.equal(matchTypeahead(labels, all, 0, 'x'), -1)
  assert.equal(matchTypeahead(labels, all, 0, ''), -1)
})

test('type-ahead keeps the current item while the word grows, and skips disabled ones', () => {
  const items = ['Archivar', 'Archivo', 'Otro']
  assert.equal(matchTypeahead(items, [true, true, true], 0, 'arch'), 0)
  assert.equal(matchTypeahead(items, [false, true, true], 0, 'arch'), 1)
})

test('a repeated letter cycles through the items that share it', () => {
  const items = ['Fijar', 'Fusionar', 'Otro', 'Fondo']
  const on = [true, true, true, true]
  assert.equal(matchTypeahead(items, on, 0, 'ff'), 1)
  assert.equal(matchTypeahead(items, on, 1, 'ff'), 3)
  assert.equal(matchTypeahead(items, on, 3, 'ff'), 0)
})

test('the type-ahead buffer grows quickly and resets after a pause', () => {
  assert.equal(nextTypeahead('', 'a', 0), 'a')
  assert.equal(nextTypeahead('a', 'r', 200), 'ar')
  assert.equal(nextTypeahead('ar', 'c', 900), 'c')
  assert.equal(nextTypeahead('a', ' ', 100), null)
  assert.equal(nextTypeahead('a', 'ArrowDown', 100), null)
})
