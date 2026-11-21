/**
 * Feature: library (plan A6). Brief: app/agents/library.md
 *
 * The Library app window (mockups Home-Library and Home-LessonDetail): the lessons cached on this Mac, a Continue
 * row, a tool filter and search, and a lesson's preview with Start lesson (library.start: zero model calls).
 *   Electron      → a normal app window (kind 'app', main/appWindows.ts); data through main/features/library.ts.
 *   Browser stage → ?window=library (&id=<lesson>); web.ts stands in for main.
 * Open it from anywhere with openLibrary(id?) from core/surfaces.ts.
 */
import { defineFeature } from '../../core/registry'
import { windowSize } from '../../core/theme'
import { LibraryWindow } from './LibraryWindow'
import './web'

export default defineFeature({
  id: 'library',
  windows: [{ route: 'library', kind: 'app', size: windowSize.library, Component: LibraryWindow }]
})
