/**
 * Feature: dashboard. The right rail (Review, Continue, Up next) and the skill card a node click opens.
 * One primary per surface: Resume on the newest lesson in progress, or, with none, Start on the first up-next lesson.
 * Everything else is a quiet button. Start review stays disabled until the engine lists review.start.
 */
import { Play, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { CodeText } from '../../core/ui/atoms'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import type { AppRoute } from '../../core/surfaces'
import { color, fill, radius2, status, surface, type2 } from '../../core/theme'
import { lessonIndex, nextFor, nodeStates, prereqs, relDay, relInLine, reviewFor, reviewIndex, shortDay, unlockLabels } from './model'
import { caption, Empty, h2, NodeGlyph, STATE_WORD } from './parts'
import { canReview, select, startGoal, startReview, startSaved, useDash } from './store'
import { contLine, type Cont } from './continue'
import type { DashData, DashNext, ReviewEntry } from './types'
import { bridge } from '../../bridge'

/** The Windows build says the same about its own machine: "this computer", never "this Mac" or the Keychain. */
const ON_MAC = bridge.platform.os === 'mac'
const HERE = ON_MAC ? 'this Mac' : 'this computer'

const row = { borderTop: `1px solid ${fill.hairline}` } as const

function Card({ id, title, right, children }: { id: string; title: string; right?: ReactNode; children: ReactNode }): ReactNode {
  return (
    <section aria-labelledby={id} className="flex shrink-0 flex-col gap-[10px]">
      <div className="flex items-baseline justify-between gap-[8px]">
        <h2 id={id} style={{ ...h2, fontSize: type2.xs, fontWeight: 500, color: color.label, letterSpacing: '0.02em' }}>
          {title}
        </h2>
        {right}
      </div>
      {children}
    </section>
  )
}

function StartError({ k }: { k: string }): ReactNode {
  const err = useDash((s) => (s.startError?.key === k ? s.startError.text : undefined))
  return err ? (
    <span role="status" style={caption}>
      {err}
    </span>
  ) : null
}

// ---- review -----------------------------------------------------------------------------------------------------

export function Review({ data, due, later, now, route }: { data?: DashData; due: ReviewEntry[]; later: ReviewEntry[]; now: number; route: AppRoute }): ReactNode {
  const can = canReview()
  return (
    <Card id="dash-review" title="Review" right={due.length ? <span className="tabular-nums" style={caption}>{due.length} due</span> : undefined}>
      {!data?.review ? (
        <Empty title="Nothing to review yet" body="Mastered skills come back here at 3, 7, 21 and 60 days." />
      ) : !due.length && !later.length ? (
        <Empty title="Nothing to review yet" body="Master a skill and it comes back here to stick." />
      ) : (
        <>
          <ul className="m-0 flex list-none flex-col p-0">
            {due.slice(0, 3).map((r, i) => (
              <li key={`d-${r.label}-${i}`} data-review-item="due" className="flex items-center gap-[10px] py-[8px]" style={i ? row : undefined}>
                <span className="block shrink-0" style={{ width: 7, height: 7, borderRadius: radius2.round, background: color.text }} />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate" style={{ fontSize: type2.sm, color: color.text }}>
                    <CodeText text={r.label} />
                  </span>
                  <span className="truncate" style={{ fontSize: type2.micro, color: color.label }}>
                    {[r.track, r.dueAt ? `Due ${relInLine(r.dueAt, now)}` : r.when ? `Due ${/^(today|tomorrow|now)$/i.test(r.when) ? r.when.toLowerCase() : r.when}` : 'Due'].filter(Boolean).join(' · ')}
                  </span>
                </div>
              </li>
            ))}
            {later.slice(0, due.length ? 2 : 4).map((r, i) => (
              <li key={`l-${r.label}-${i}`} data-review-item="later" className="flex items-center justify-between gap-[10px] py-[7px]" style={i || due.length ? row : undefined}>
                <span className="min-w-0 truncate" style={caption}>
                  <CodeText text={r.label} />
                </span>
                <span className="shrink-0" style={{ fontSize: type2.micro, color: color.faint }}>
                  {r.dueAt ? relDay(r.dueAt, now) : r.when}
                </span>
              </li>
            ))}
          </ul>
          {due.length > 0 && (
            <QuietButton
              label="Start review"
              block
              disabled={!can}
              title={can ? `One short step on ${due[0].label.split(String.fromCharCode(96)).join('')}` : 'miyagi can’t start reviews yet'}
              onClick={() => startReview(due[0], route)}
            />
          )}
        </>
      )}
    </Card>
  )
}

// ---- continue ---------------------------------------------------------------------------------------------------

export function Continue({ items, route }: { items: Cont[]; route: AppRoute }): ReactNode {
  const starting = useDash((s) => s.starting)
  if (!items.length) return null
  return (
    <Card id="dash-continue" title="Continue">
      <ul className="m-0 flex list-none flex-col gap-[14px] p-0">
        {items.slice(0, 3).map((c, i) => {
          const Btn = i === 0 ? PrimaryButton : QuietButton
          return (
            <li key={c.libraryId} data-continue={c.libraryId} className="flex items-center gap-[16px]">
              <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
                <span className="font-medium" style={{ fontSize: type2.body, color: color.text }}>
                  {c.title}
                </span>
                <span style={caption}>{contLine(c)}</span>
              </div>
              <Btn label="Continue" icon={Play} busy={starting === c.libraryId} disabled={!!starting && starting !== c.libraryId} onClick={() => void startSaved(c.libraryId, route)} />
              <StartError k={c.libraryId} />
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

// ---- up next ----------------------------------------------------------------------------------------------------

function NextRow({ n, data, primary, route, first }: { n: DashNext; data?: DashData; primary?: string; route: AppRoute; first: boolean }): ReactNode {
  const starting = useDash((s) => s.starting)
  const key = `next:${n.title}`
  const Btn = primary === key ? PrimaryButton : QuietButton
  const unlocks = unlockLabels(data, n.unlocks)
  return (
    <li data-next={n.title} className="flex flex-col gap-[8px]" style={first ? undefined : { ...row, paddingTop: 12 }}>
      <div className="flex min-w-0 flex-col gap-[2px]">
        <span style={{ fontSize: type2.sm, fontWeight: 500, color: color.text }}>{n.title}</span>
        {unlocks.length > 0 && (
          <span style={caption}>
            Unlocks <CodeText text={unlocks.join(', ')} />
          </span>
        )}
        {n.estMinutes ? <span style={{ fontSize: type2.micro, color: color.faint }}>About {n.estMinutes} min</span> : null}
      </div>
      <Btn
        label="Start"
        block
        busy={!!n.id && starting === n.id}
        disabled={!!starting}
        title={n.id ? `Saved on ${HERE}` : 'miyagi builds this lesson for you'}
        onClick={() => (n.id ? void startSaved(n.id, route) : startGoal(n.goal, route))}
      />
      {n.id && <StartError k={n.id} />}
    </li>
  )
}

export function UpNext({ data, primary, route }: { data?: DashData; primary?: string; route: AppRoute }): ReactNode {
  const next = data?.next ?? []
  return (
    <Card id="dash-next" title="Up next">
      {!next.length ? (
        <Empty title="Nothing queued yet" body="Finish a lesson and miyagi suggests what comes next." />
      ) : (
        <ul className="m-0 flex list-none flex-col gap-[12px] p-0">
          {next.slice(0, 3).map((n, i) => (
            <NextRow key={n.title} n={n} data={data} primary={primary} route={route} first={i === 0} />
          ))}
        </ul>
      )}
    </Card>
  )
}

// ---- skill card -------------------------------------------------------------------------------------------------

export function SkillCard({ data, now, route }: { data?: DashData; now: number; route: AppRoute }): ReactNode {
  const sel = useDash((s) => s.selected)
  const starting = useDash((s) => s.starting)
  const t = data?.tracks.find((x) => x.track === sel?.track)
  const s = t?.skills.find((x) => x.id === sel?.id)
  if (!t || !s) return null
  const st = nodeStates(t)[s.id]
  const review = data?.review ? reviewFor(reviewIndex(data.review.items), s) : undefined
  const due = st === 'mastered' && !!review && (review.dueAt !== undefined ? review.dueAt <= now : true)
  const lessons = lessonIndex(data)
  const taught = s.lessons.map((id) => lessons.get(id)).filter((x): x is NonNullable<typeof x> => !!x)
  const ups = nextFor(data, s)
  const missing = prereqs(t, s.id)
    .map((id) => t.skills.find((x) => x.id === id))
    .filter((x) => x && x.state !== 'mastered')
    .map((x) => x!.label)
  const facts = [
    s.reps !== undefined ? `${s.reps} ${s.reps === 1 ? 'rep' : 'reps'}` : '',
    s.masteredAt ? `Mastered ${shortDay(s.masteredAt)}` : '',
    s.lastPracticedAt ? `Practiced ${relInLine(s.lastPracticedAt, now)}` : ''
  ].filter(Boolean)
  const hint =
    st === 'practicing'
      ? 'Pass its steps with your own work to master it.'
      : st === 'locked' && missing.length
        ? `Opens after ${missing.join(' and ')}.`
        : st === 'available'
          ? 'Everything it needs is mastered.'
          : undefined
  return (
    <div
      data-skill-card={s.id}
      role="dialog"
      aria-label={s.label.split(String.fromCharCode(96)).join('')}
      className="absolute z-20 flex flex-col gap-[12px] overflow-y-auto"
      style={{ top: 16, right: 16, width: 300, maxHeight: 'calc(100% - 32px)', padding: 16, borderRadius: radius2.group, background: surface.sheet, boxShadow: `inset 0 0 0 1px ${surface.border}, ${surface.shadow}` }}
    >
      <div className="flex items-start gap-[10px]">
        <NodeGlyph state={st} due={due} />
        <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
          <span style={{ fontSize: type2.body, fontWeight: 600, color: color.text }}>
            <CodeText text={s.label} />
          </span>
          <span style={{ fontSize: type2.xs, color: st === 'mastered' ? status.passed : color.label }}>
            {STATE_WORD[st]} · {t.track}
          </span>
        </div>
        <button type="button" aria-label="Close" className="flex shrink-0 cursor-pointer items-center justify-center" style={{ width: 24, height: 24, borderRadius: radius2.round, background: fill.key, color: fill.keyText }} onClick={() => select(undefined)}>
          <X size={13} strokeWidth={2} aria-hidden />
        </button>
      </div>
      {s.detail && <span style={{ fontSize: type2.sm, lineHeight: '18px', color: color.text }}>{s.detail}</span>}
      {hint && <span style={caption}>{hint}</span>}
      {(facts.length > 0 || review) && (
        <span style={caption}>
          {[...facts, review ? (due ? 'Review due' : review.dueAt ? `Next review ${shortDay(review.dueAt)}` : '') : ''].filter(Boolean).join(' · ')}
        </span>
      )}
      {taught.length > 0 && (
        <div className="flex flex-col gap-[6px]">
          <span style={{ fontSize: type2.micro, fontWeight: 600, color: color.label, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Taught in</span>
          {taught.map((l) => (
            <div key={l.lessonId} className="flex items-center gap-[8px]">
              <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.sm, color: color.text }} title={l.title}>
                {l.title}
              </span>
              <QuietButton
                label={l.inProgress ? 'Resume' : 'Again'}
                busy={!!l.libraryId && starting === l.libraryId}
                disabled={!l.libraryId || !!starting}
                title={l.libraryId ? undefined : `Not saved on ${HERE}`}
                onClick={() => l.libraryId && void startSaved(l.libraryId, route)}
              />
            </div>
          ))}
        </div>
      )}
      {ups.length > 0 && (
        <div className="flex flex-col gap-[6px]">
          <span style={{ fontSize: type2.micro, fontWeight: 600, color: color.label, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Learn it in</span>
          {ups.map((n) => (
            <div key={n.title} className="flex items-center gap-[8px]">
              <span className="min-w-0 flex-1 truncate" style={{ fontSize: type2.sm, color: color.text }} title={n.title}>
                {n.title}
              </span>
              <QuietButton label="Start" busy={!!n.id && starting === n.id} disabled={!!starting} onClick={() => (n.id ? void startSaved(n.id, route) : startGoal(n.goal, route))} />
            </div>
          ))}
        </div>
      )}
      {!taught.length && !ups.length && st !== 'mastered' && <span style={caption}>No lesson for it on {HERE} yet. Ask miyagi for one.</span>}
      {[...taught.map((l) => l.libraryId), ...ups.map((n) => n.id)].filter((x): x is string => !!x).map((k) => (
        <StartError key={k} k={k} />
      ))}
    </div>
  )
}
