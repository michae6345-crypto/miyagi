/**
 * Feature: demo. A tiny Python highlighter for the fake VS Code, in Dark Modern's colors (the learner's editor,
 * not miyagi's UI). Enough for nn.py: comments, strings, numbers, keywords, calls, the np module, brackets.
 */
import type { ReactNode } from 'react'

const C = {
  text: '#CCCCCC',
  comment: '#6A9955',
  string: '#CE9178',
  number: '#B5CEA8',
  control: '#C586C0',
  storage: '#569CD6',
  fn: '#DCDCAA',
  module: '#4EC9B0',
  variable: '#9CDCFE',
  brackets: ['#FFD700', '#DA70D6', '#179FFF']
} as const

const CONTROL = new Set(['import', 'as', 'return', 'for', 'in', 'if', 'from', 'while', 'else', 'elif'])
const STORAGE = new Set(['def', 'True', 'False', 'None', 'and', 'or', 'not', 'lambda'])
const BUILTIN = new Set(['print', 'len', 'range', 'int', 'float'])

const TOKEN = /(#.*$)|(f?"[^"]*"?)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)|([()[\]{}])|(\s+)|(.)/g

export function highlight(line: string): ReactNode[] {
  const out: ReactNode[] = []
  let depth = 0
  let m: RegExpExecArray | null
  let i = 0
  TOKEN.lastIndex = 0
  while ((m = TOKEN.exec(line))) {
    const [tok, comment, str, num, word, bracket] = m
    let color: string = C.text
    if (comment) color = C.comment
    else if (str) color = C.string
    else if (num) color = C.number
    else if (word) {
      const after = line.slice(TOKEN.lastIndex).trimStart()
      if (CONTROL.has(word)) color = C.control
      else if (STORAGE.has(word)) color = C.storage
      else if (word === 'np') color = C.module
      else if (BUILTIN.has(word) || after.startsWith('(')) color = C.fn
      else color = C.variable
    } else if (bracket) {
      const open = '([{'.includes(bracket)
      if (!open) depth = Math.max(0, depth - 1)
      color = C.brackets[depth % 3]
      if (open) depth++
    }
    out.push(
      <span key={i++} style={{ color }}>
        {tok}
      </span>
    )
    if (!tok) break
  }
  return out
}
