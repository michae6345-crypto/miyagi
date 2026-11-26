/**
 * Feature: settings. A live sample of the code settings (Editor): the same size variable, line counter and wrap rule
 * the lesson cards use (styles.css, apply.ts), so a change shows here as it will show there.
 */
import type { ReactNode } from 'react'
import { color, fill, font, radius2, type2 } from '../../core/theme'
import { CODE_SAMPLE, CODE_SAMPLE_CAPTION } from './sample'

export function CodePreview(): ReactNode {
  return (
    <section aria-label="Preview" data-settings-preview style={{ borderRadius: radius2.card, background: fill.group, boxShadow: `inset 0 0 0 1px ${fill.hairline}`, overflow: 'hidden' }}>
      <div className="flex h-[32px] items-center px-[16px]" style={{ borderBottom: `1px solid ${fill.hairline}`, fontSize: type2.xs, color: color.label }}>
        {CODE_SAMPLE_CAPTION}
      </div>
      <pre data-code-pre className="m-0 overflow-x-auto whitespace-pre px-[16px] py-[12px] leading-[20px]" style={{ fontFamily: font.mono, fontSize: 'var(--mg-code-size, 12px)', color: color.text, background: fill.field }}>
        <code>
          {CODE_SAMPLE.split('\n').map((line, i) => (
            <span key={i} data-code-line className="block">
              {line || ' '}
            </span>
          ))}
        </code>
      </pre>
    </section>
  )
}
