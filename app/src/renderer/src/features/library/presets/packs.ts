/**
 * Feature: library / presets. The curated starter packs (data only: no UI code, nothing lesson-specific elsewhere).
 * Placeholder for now: a pack is a name, a line, a size and a topic. Adding one only marks it on this Mac (store.ts).
 * `short` is what the button says ("Download C++"); `mark` is the two or three letters on the tile (monochrome, no
 * brand colors or logos).
 */
export type Topic = 'code' | 'data' | 'ai' | 'design' | '3d' | 'tools'

export const TOPICS: ReadonlyArray<{ id: Topic; label: string }> = [
  { id: 'code', label: 'Code' },
  { id: 'data', label: 'Data' },
  { id: 'ai', label: 'AI' },
  { id: 'design', label: 'Design' },
  { id: '3d', label: '3D' },
  { id: 'tools', label: 'Tools' }
]

export type Pack = {
  id: string
  name: string
  short: string
  mark: string
  line: string
  topic: Topic
  lessons: number
  /** Total minutes, shown as "about 3 hr". */
  minutes: number
}

export const PACKS: ReadonlyArray<Pack> = [
  { id: 'cpp', name: 'C++', short: 'C++', mark: 'C++', line: 'Types, pointers and the standard library, one program at a time.', topic: 'code', lessons: 14, minutes: 280 },
  { id: 'python', name: 'Python basics', short: 'Python', mark: 'Py', line: 'Variables, loops, functions and files. Your first real scripts.', topic: 'code', lessons: 12, minutes: 200 },
  { id: 'javascript', name: 'JavaScript', short: 'JavaScript', mark: 'JS', line: 'The language of the browser, from values to async code.', topic: 'code', lessons: 13, minutes: 240 },
  { id: 'typescript', name: 'TypeScript', short: 'TypeScript', mark: 'TS', line: 'Add types to JavaScript and let the editor catch mistakes.', topic: 'code', lessons: 9, minutes: 150 },
  { id: 'react', name: 'React', short: 'React', mark: 'Re', line: 'Components, state and effects. Build a small app.', topic: 'code', lessons: 11, minutes: 210 },
  { id: 'swift', name: 'Swift for iOS', short: 'Swift', mark: 'Sw', line: 'Swift and SwiftUI, from a blank file to a running app.', topic: 'code', lessons: 15, minutes: 300 },
  { id: 'rust', name: 'Rust', short: 'Rust', mark: 'Rs', line: 'Ownership and borrowing, made small enough to hold.', topic: 'code', lessons: 12, minutes: 260 },
  { id: 'numpy', name: 'NumPy', short: 'NumPy', mark: 'Np', line: 'Arrays, slicing and broadcasting without the loops.', topic: 'data', lessons: 8, minutes: 120 },
  { id: 'pandas', name: 'pandas', short: 'pandas', mark: 'Pd', line: 'Load, clean, group and reshape a table of data.', topic: 'data', lessons: 10, minutes: 170 },
  { id: 'matplotlib', name: 'Plotting with matplotlib', short: 'matplotlib', mark: 'Mp', line: 'Line, bar and scatter plots that say what you mean.', topic: 'data', lessons: 6, minutes: 90 },
  { id: 'sql', name: 'SQL', short: 'SQL', mark: 'SQL', line: 'Select, join and aggregate. Ask a database real questions.', topic: 'data', lessons: 11, minutes: 190 },
  { id: 'sheets', name: 'Google Sheets', short: 'Sheets', mark: 'Gs', line: 'Formulas, filters and pivot tables for everyday numbers.', topic: 'tools', lessons: 8, minutes: 110 },
  { id: 'excel', name: 'Excel formulas', short: 'Excel', mark: 'Xl', line: 'Lookups, text and dates. The formulas you reach for most.', topic: 'tools', lessons: 9, minutes: 130 },
  { id: 'pytorch', name: 'PyTorch', short: 'PyTorch', mark: 'Pt', line: 'Tensors, autograd and a training loop you write yourself.', topic: 'ai', lessons: 10, minutes: 210 },
  { id: 'nn', name: 'Neural networks from scratch', short: 'Neural nets', mark: 'NN', line: 'Build a small network with plain arrays and train it.', topic: 'ai', lessons: 9, minutes: 190 },
  { id: 'sklearn', name: 'scikit-learn', short: 'scikit-learn', mark: 'Sk', line: 'Fit, score and compare classic models on real data.', topic: 'ai', lessons: 8, minutes: 150 },
  { id: 'prompting', name: 'Working with language models', short: 'LLM basics', mark: 'LM', line: 'Prompts, context and checking what a model gives back.', topic: 'ai', lessons: 6, minutes: 100 },
  { id: 'figma', name: 'Figma basics', short: 'Figma', mark: 'Fg', line: 'Frames, components and a first screen you can share.', topic: 'design', lessons: 8, minutes: 130 },
  { id: 'autolayout', name: 'Figma auto layout', short: 'Auto layout', mark: 'Al', line: 'Make designs that resize without you moving every piece.', topic: 'design', lessons: 5, minutes: 75 },
  { id: 'type', name: 'Type and spacing', short: 'Type', mark: 'Aa', line: 'Pick a scale, set a rhythm, and fix crowded layouts.', topic: 'design', lessons: 6, minutes: 80 },
  { id: 'blender', name: 'Blender basics', short: 'Blender', mark: 'Bl', line: 'Navigate the scene, model a mug and render it.', topic: '3d', lessons: 12, minutes: 240 },
  { id: 'threejs', name: 'Three.js', short: 'Three.js', mark: '3js', line: 'A scene, a camera and a light. Then something that moves.', topic: '3d', lessons: 9, minutes: 160 },
  { id: 'git', name: 'Git and GitHub', short: 'Git', mark: 'Git', line: 'Commit, branch, merge and open your first pull request.', topic: 'tools', lessons: 9, minutes: 140 },
  { id: 'linux', name: 'Linux command line', short: 'Linux', mark: 'Sh', line: 'Move around, search, pipe and script from the terminal.', topic: 'tools', lessons: 10, minutes: 160 },
  { id: 'docker', name: 'Docker', short: 'Docker', mark: 'Dk', line: 'Images, containers and a compose file that just runs.', topic: 'tools', lessons: 7, minutes: 120 }
]

/** "12 lessons" and "about 3 hr" / "about 75 min". */
export const lessonsLabel = (n: number): string => `${n} ${n === 1 ? 'lesson' : 'lessons'}`
export function aboutLabel(min: number): string {
  if (min < 90) return `about ${Math.round(min / 5) * 5} min`
  const h = Math.round((min / 60) * 2) / 2
  return `about ${h} hr`
}
