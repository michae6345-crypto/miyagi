/** core/editKeys.ts: the editing keys a non-activating panel's field may get without an edit command (user report, main 1d453ca0). */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { editFor, lineEnd, lineStart, wordBack, wordFwd, type Mods } from '../src/renderer/src/core/editKeys'

const none: Mods = { alt: false, meta: false, shift: false, ctrl: false }
const alt: Mods = { ...none, alt: true }
const meta: Mods = { ...none, meta: true }
const shift: Mods = { ...none, shift: true }

describe('edit keys', () => {
  test('Backspace deletes the character before the caret', () => {
    assert.deepEqual(editFor('Backspace', none, 'hello', 5, 5), { kind: 'delete', from: 4, to: 5 })
    assert.deepEqual(editFor('Backspace', none, 'hello', 2, 2), { kind: 'delete', from: 1, to: 2 })
  })
  test('Backspace at the start does nothing', () => {
    assert.equal(editFor('Backspace', none, 'hello', 0, 0), undefined)
    assert.equal(editFor('Backspace', none, '', 0, 0), undefined)
  })
  test('Backspace or Delete with a selection deletes the selection', () => {
    assert.deepEqual(editFor('Backspace', none, 'hello world', 2, 7), { kind: 'delete', from: 2, to: 7 })
    assert.deepEqual(editFor('Delete', alt, 'hello world', 2, 7), { kind: 'delete', from: 2, to: 7 })
  })
  test('Backspace takes a whole emoji (surrogate pair)', () => {
    const v = 'ok 👍'
    assert.deepEqual(editFor('Backspace', none, v, v.length, v.length), { kind: 'delete', from: 3, to: 5 })
  })
  test('⌥⌫ deletes the word before the caret, ⌘⌫ to the line start', () => {
    assert.deepEqual(editFor('Backspace', alt, 'how do I loop', 13, 13), { kind: 'delete', from: 9, to: 13 })
    assert.deepEqual(editFor('Backspace', alt, 'loop  ', 6, 6), { kind: 'delete', from: 0, to: 6 })
    assert.deepEqual(editFor('Backspace', meta, 'how do I loop', 8, 8), { kind: 'delete', from: 0, to: 8 })
    assert.deepEqual(editFor('Backspace', meta, 'a\nbc', 4, 4), { kind: 'delete', from: 2, to: 4 })
  })
  test('Delete deletes forward; ⌥⌦ a word, ⌘⌦ to the line end', () => {
    assert.deepEqual(editFor('Delete', none, 'hello', 0, 0), { kind: 'delete', from: 0, to: 1 })
    assert.equal(editFor('Delete', none, 'hello', 5, 5), undefined)
    assert.deepEqual(editFor('Delete', alt, 'how do', 0, 0), { kind: 'delete', from: 0, to: 3 })
    assert.deepEqual(editFor('Delete', meta, 'ab\ncd', 1, 1), { kind: 'delete', from: 1, to: 2 })
  })
  test('⌃ combinations and other keys are left alone', () => {
    assert.equal(editFor('Backspace', { ...none, ctrl: true }, 'abc', 3, 3), undefined)
    assert.equal(editFor('x', none, 'abc', 3, 3), undefined)
    assert.equal(editFor('Enter', none, 'abc', 3, 3), undefined)
  })
  test('⌘A selects everything, once', () => {
    assert.deepEqual(editFor('a', meta, 'abc', 1, 1), { kind: 'select', from: 0, to: 3, dir: 'none' })
    assert.equal(editFor('a', meta, 'abc', 0, 3), undefined)
  })
  test('← and → move the caret, collapse a selection, ⇧ extends, ⌥ by word, ⌘ to the line', () => {
    assert.deepEqual(editFor('ArrowLeft', none, 'abc', 2, 2), { kind: 'select', from: 1, to: 1, dir: 'none' })
    assert.deepEqual(editFor('ArrowRight', none, 'abc', 2, 2), { kind: 'select', from: 3, to: 3, dir: 'none' })
    assert.equal(editFor('ArrowLeft', none, 'abc', 0, 0), undefined)
    assert.equal(editFor('ArrowRight', none, 'abc', 3, 3), undefined)
    assert.deepEqual(editFor('ArrowLeft', none, 'abcdef', 1, 4), { kind: 'select', from: 1, to: 1, dir: 'none' })
    assert.deepEqual(editFor('ArrowRight', none, 'abcdef', 1, 4), { kind: 'select', from: 4, to: 4, dir: 'none' })
    assert.deepEqual(editFor('ArrowLeft', shift, 'abc', 2, 2), { kind: 'select', from: 1, to: 2, dir: 'backward' })
    assert.deepEqual(editFor('ArrowLeft', alt, 'how do', 6, 6), { kind: 'select', from: 4, to: 4, dir: 'none' })
    assert.deepEqual(editFor('ArrowRight', meta, 'how do', 1, 1), { kind: 'select', from: 6, to: 6, dir: 'none' })
  })
  test('word and line edges', () => {
    assert.equal(wordBack('foo.bar', 7), 4)
    assert.equal(wordBack('foo. ', 5), 0)
    assert.equal(wordFwd('foo bar', 3), 7)
    assert.equal(lineStart('ab\ncd', 5), 3)
    assert.equal(lineStart('ab\ncd', 3), 3)
    assert.equal(lineStart('ab', 0), 0)
    assert.equal(lineEnd('ab\ncd', 0), 2)
    assert.equal(lineEnd('ab\ncd', 4), 5)
  })

  test('⇧←/⇧→ move the selection focus, keeping its anchor (selectionDirection)', () => {
    // forward selection 1..4 (anchor 1, focus 4): ⇧← shrinks it from the end, ⇧→ grows it.
    assert.deepEqual(editFor('ArrowLeft', shift, 'abcdef', 1, 4, 'forward'), { kind: 'select', from: 1, to: 3, dir: 'forward' })
    assert.deepEqual(editFor('ArrowRight', shift, 'abcdef', 1, 4, 'forward'), { kind: 'select', from: 1, to: 5, dir: 'forward' })
    // backward selection 1..4 (anchor 4, focus 1): ⇧← grows it at the start, ⇧→ shrinks it from the start.
    assert.deepEqual(editFor('ArrowLeft', shift, 'abcdef', 1, 4, 'backward'), { kind: 'select', from: 0, to: 4, dir: 'backward' })
    assert.deepEqual(editFor('ArrowRight', shift, 'abcdef', 1, 4, 'backward'), { kind: 'select', from: 2, to: 4, dir: 'backward' })
    // crossing the anchor flips the direction
    assert.deepEqual(editFor('ArrowLeft', shift, 'abcdef', 2, 3, 'forward'), { kind: 'select', from: 2, to: 2, dir: 'none' })
    assert.deepEqual(editFor('ArrowRight', shift, 'abcdef', 2, 3, 'backward'), { kind: 'select', from: 3, to: 3, dir: 'none' })
    // 'none' (the Mac's default) behaves as forward
    assert.deepEqual(editFor('ArrowRight', shift, 'abcdef', 1, 4), { kind: 'select', from: 1, to: 5, dir: 'forward' })
  })
})
