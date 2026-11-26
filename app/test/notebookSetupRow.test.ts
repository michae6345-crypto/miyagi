/**
 * Nov 26 user test (TensorFlow MNIST notebook lesson): the engine's "Python and Jupyter for VS Code" row (install.method
 * "vscode_ext": `code --install-extension`, run by the engine on Install) is an Install row like pip / brew, so the
 * setup card's primary is Install for it (cards/store.ts engineInstalls and setupPlan.ts PACKAGE list the method).
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Payload } from '../src/common/wire'
import { planSetup, toolKind } from '../src/renderer/src/features/cards/setupPlan'

type Card = Payload<'card'>
type Item = NonNullable<Card['setup']>['items'][number]

const row = (over: Partial<Item> = {}): Item => ({
  tool: 'vscode-jupyter',
  label: 'Python and Jupyter for VS Code',
  kind: 'cli',
  why: "VS Code runs the notebook's cells with them, on the lesson's .venv.",
  needed: true,
  installed: false,
  ok: false,
  install: { method: 'vscode_ext', command: 'code --install-extension ms-python.python --install-extension ms-toolsai.jupyter' },
  setupKind: 'package',
  actions: ['install', 'skip'],
  ...over
})

const kernel: Item = { ...row(), tool: 'ipykernel', label: 'Jupyter kernel (ipykernel)', kind: 'python_package', install: { method: 'pip', command: 'pip install ipykernel' } }

test('the VS Code extensions row installs through the engine like pip', () => {
  assert.equal(toolKind(row()), 'install')
  assert.equal(toolKind(kernel), 'install')
})

test('a notebook setup card leads with Install', () => {
  const card: Card = { kind: 'setup', title: 'Before the lesson', body: '', actions: ['install_all', 'install', 'skip_setup'], setup: { editorNeeded: true, items: [row(), kernel] } } as Card
  const p = planSetup(card)
  assert.ok(p.primary && /install/i.test(String(p.primary.action ?? p.primary.label)), JSON.stringify(p.primary))
})
