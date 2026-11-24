/**
 * Feature: plans. The two "new plan" dialogs (Adrian's mocks plan-playlist and plan-goal, 23-lesson-plans-10..17).
 *
 *   From a playlist  paste a YouTube playlist link; the playlist's videos become lessons, each growing one skill, and
 *                    the plan can end with the project of the plan it matches. "Just the first video" adds one lesson.
 *   From a goal      say what you want to make; pick where you work (option chips, the one pastel use here), and the
 *                    plan is put together from the catalog's plans, ending in a project.
 *
 * Offline until the contract's plan messages land: playlists are matched against catalog/playlists.json (50 fetched
 * Nov 22) and goals against the catalog's own words (catalog.ts planFromGoal). Anything else says so plainly.
 */
import { Flag, Link2, X } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { color, elevation, fill, radius2, scrim, surface, tone, type Tone, type2 } from '../../core/theme'
import { aboutHours, lengthLabel, planById, planFromGoal, playlistById, playlistIdOf, skillLabel, type Playlist } from './catalog'
import { addPlan, closeDialog, usePlans } from './store'
import { Thumb, artFor } from './Thumb'
import { hair, meta, SkillChip, TableHead, TableRow } from './ui'

export function PlanDialogs(): ReactNode {
  const dialog = usePlans((s) => s.dialog)
  useEffect(() => {
    if (!dialog) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        closeDialog()
      }
    }
    addEventListener('keydown', onKey, true)
    return () => removeEventListener('keydown', onKey, true)
  }, [dialog])
  if (!dialog) return null
  return (
    <div data-plan-dialog={dialog} className="fixed inset-0 z-40 flex items-start justify-center" style={{ padding: '120px 24px 24px', background: scrim.launcher }} onMouseDown={(e) => e.target === e.currentTarget && closeDialog()}>
      <div role="dialog" aria-modal aria-label={dialog === 'playlist' ? 'New plan from a playlist' : 'New plan from a goal'} className="flex max-h-full w-full flex-col overflow-hidden" style={{ maxWidth: 740, borderRadius: radius2.panel, background: surface.sheet, boxShadow: `inset 0 0 0 1px ${surface.border}, ${elevation.overlay}`, color: color.text }}>
        {dialog === 'playlist' ? <PlaylistDialog /> : <GoalDialog />}
      </div>
    </div>
  )
}

function Head({ title }: { title: string }): ReactNode {
  return (
    <div className="flex shrink-0 items-center justify-between" style={{ padding: '22px 24px 14px' }}>
      <h2 className="m-0" style={{ fontSize: type2.xl, lineHeight: '26px', fontWeight: 700, letterSpacing: '-0.3px' }}>
        {title}
      </h2>
      <button type="button" aria-label="Close" onClick={closeDialog} className="flex cursor-pointer items-center justify-center" style={{ width: 28, height: 28, borderRadius: radius2.round, background: 'none', border: 0, color: color.label }}>
        <X size={17} strokeWidth={1.8} />
      </button>
    </div>
  )
}

function Field({ icon, value, onChange, placeholder, label }: { icon: ReactNode; value: string; onChange: (v: string) => void; placeholder: string; label: string }): ReactNode {
  return (
    <label className="flex shrink-0 items-center gap-[10px]" style={{ margin: '0 24px', height: 44, padding: '0 14px', borderRadius: radius2.card, background: surface.well, boxShadow: `inset 0 0 0 1.5px ${color.text}` }}>
      <span style={{ color: color.label, display: 'flex' }}>{icon}</span>
      <input autoFocus aria-label={label} value={value} placeholder={placeholder} spellCheck={false} onChange={(e) => onChange(e.target.value.slice(0, 300))} className="min-w-0 flex-1" style={{ background: 'none', border: 0, outline: 'none', color: color.text, fontSize: type2.body }} />
    </label>
  )
}

function Foot({ note, children }: { note: string; children: ReactNode }): ReactNode {
  return (
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-[12px]" style={{ padding: '16px 24px 22px' }}>
      <span style={meta}>{note}</span>
      <div className="flex items-center gap-[10px]">{children}</div>
    </div>
  )
}

// ---- from a playlist ------------------------------------------------------------------------------------------------

const SHOWN = 6

function PlaylistDialog(): ReactNode {
  const [link, setLink] = useState('')
  const [picked, setPicked] = useState<Record<number, boolean>>({})
  const [project, setProject] = useState(true)
  const id = playlistIdOf(link)
  const list: Playlist | undefined = playlistById(id)
  const plan = planById(list?.planId)
  useEffect(() => setPicked({}), [id])
  const on = (i: number): boolean => picked[i] !== false
  const chosen = list ? list.videos.filter((_, i) => on(i)) : []
  // A video grows the plan skill its title names ("Materials Tutorial" → Materials), else the skill of the plan's
  // lesson at the same place. The contract's playlist answer will name it instead.
  const grows = (i: number): string | undefined => {
    const title = list?.videos[i]?.title.toLowerCase() ?? ''
    const named = plan?.skills.find((s) => s.label.toLowerCase().split(/[^a-z]+/).some((w) => w.length > 3 && title.includes(w)))
    if (named) return named.label
    const l = plan?.lessons[Math.min(i, (plan?.lessons.length ?? 1) - 1)]
    return l ? (skillLabel(l.grows[0]) ?? l.grows[0]) : undefined
  }
  const skills = new Set(chosen.map((_, i) => grows(i)).filter(Boolean)).size
  const add = (first: boolean): void => {
    if (!list || !plan) return
    const videos = first ? list.videos.slice(0, 1) : chosen
    addPlan({
      id: `playlist:${list.playlistId}`,
      title: list.title,
      total: videos.length,
      minutesLeft: Math.round(videos.reduce((n, v) => n + v.seconds, 0) / 60),
      art: plan.id,
      source: 'playlist',
      project: project && !first ? plan.project.title : undefined,
      lessons: videos.map((v, i) => ({ ...plan.lessons[Math.min(i, plan.lessons.length - 1)], title: v.title, minutes: Math.round(v.seconds / 60), goal: `Teach me along with the video "${v.title}" by ${list.channel}.` }))
    })
  }
  const template = '24px minmax(0,1fr) minmax(0,190px) 64px'
  return (
    <>
      <Head title="New plan from a playlist" />
      <Field icon={<Link2 size={16} strokeWidth={1.8} />} value={link} onChange={setLink} placeholder="youtube.com/playlist?list=…" label="YouTube playlist link" />
      <div className="min-h-0 overflow-y-auto" style={{ padding: '16px 24px 0' }}>
        {!list ? (
          <p className="m-0" style={{ ...meta, padding: '8px 0 4px' }}>
            {link.trim() ? (id ? 'miyagi doesn’t know that playlist yet.' : 'That doesn’t look like a playlist link.') : 'Paste the link of a YouTube playlist. Each video becomes a lesson.'}
          </p>
        ) : (
          <>
            <div className="flex items-center gap-[14px]">
              <Thumb art={artFor(plan)} w={96} h={54} />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate" style={{ fontSize: type2.body, fontWeight: 600 }}>
                  {list.title}
                </span>
                <span className="truncate" style={meta}>
                  {list.channel} · {list.videoCount} videos · {lengthLabel(list.totalSeconds)}
                </span>
              </div>
              <div className="flex shrink-0 flex-col items-end">
                <span style={{ fontSize: type2.body, fontWeight: 600 }}>
                  {chosen.length} lessons · {skills} skills
                </span>
                <span style={meta}>You have none of these skills yet</span>
              </div>
            </div>
            <div role="table" aria-label="Videos" style={{ marginTop: 16 }}>
              <TableHead cols={[{ label: '' }, { label: 'Video' }, { label: 'Becomes a lesson that grows' }, { label: 'Length', align: 'right' }]} template={template} />
              {list.videos.slice(0, SHOWN).map((v, i) => (
                <TableRow key={i} template={template} height={44} label={v.title}>
                  <input type="checkbox" aria-label={`Include ${v.title}`} checked={on(i)} onChange={(e) => setPicked((p) => ({ ...p, [i]: e.target.checked }))} style={{ width: 16, height: 16, accentColor: color.text }} />
                  <span className="truncate" style={{ fontWeight: 600, opacity: on(i) ? 1 : 0.5 }}>
                    {v.title}
                  </span>
                  <span>{grows(i) && <SkillChip>{grows(i)}</SkillChip>}</span>
                  <span style={{ ...meta, textAlign: 'right' }}>{Math.round(v.seconds / 60)} min</span>
                </TableRow>
              ))}
              {list.videos.length > SHOWN && <div style={{ ...meta, padding: '12px 0 0 40px' }}>{list.videos.length - SHOWN} more videos</div>}
            </div>
            {plan && (
              <label className="flex cursor-pointer items-center gap-[12px]" style={{ marginTop: 16, minHeight: 44, borderTop: hair }}>
                <Flag size={15} strokeWidth={1.6} style={{ color: color.label }} />
                <span style={{ fontSize: type2.md, fontWeight: 600 }}>Ends with a project</span>
                <span className="min-w-0 flex-1 truncate" style={meta}>
                  {plan.project.title}, on your own
                </span>
                <Toggle on={project} onChange={setProject} label="Ends with a project" />
              </label>
            )}
          </>
        )}
      </div>
      <Foot note={plan ? `miyagi pauses each video until your ${plan.lessons.some((l) => l.check === 'scene') ? 'scene' : 'work'} passes the step.` : 'miyagi pauses each video until your work passes the step.'}>
        <QuietButton label="Just the first video" onClick={() => add(true)} disabled={!list} />
        <PrimaryButton label="Add plan" onClick={() => add(false)} disabled={!list || !chosen.length} />
      </Foot>
    </>
  )
}

function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }): ReactNode {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(!on)} className="relative shrink-0 cursor-pointer" style={{ width: 40, height: 24, borderRadius: radius2.round, border: 0, background: on ? color.text : fill.track }}>
      <span className="absolute block transition-transform duration-200" style={{ top: 3, left: 3, width: 18, height: 18, borderRadius: radius2.round, background: surface.sheet, transform: `translateX(${on ? 16 : 0}px)` }} />
    </button>
  )
}

// ---- from a goal ----------------------------------------------------------------------------------------------------

/** The tool picker's option pastels, in order (an option, so a pastel is allowed; the same order every time). */
const TOOL_TONES: Tone[] = ['sky', 'lilac', 'pink', 'mint', 'peach', 'sand']

function GoalDialog(): ReactNode {
  const [goal, setGoal] = useState('')
  const [tool, setTool] = useState<string | undefined>()
  const [typed, setTyped] = useState('')
  // Settle on the goal a moment after typing stops, so the table doesn't jump on every key.
  useEffect(() => {
    const t = setTimeout(() => setTyped(goal), 250)
    return () => clearTimeout(t)
  }, [goal])
  const built = useMemo(() => planFromGoal(typed, tool), [typed, tool])
  const base = built.from[0]
  const chosenTool = tool ?? base?.tool.id
  const minutes = built.lessons.reduce((n, l) => n + l.minutes, 0) + (built.project?.minutes ?? 0)
  const add = (): void => {
    if (!base) return
    addPlan({
      id: `goal:${typed.trim().toLowerCase().slice(0, 60)}`,
      title: typed.trim().replace(/^i want to /i, '').replace(/^./, (c) => c.toUpperCase()),
      total: built.lessons.length,
      minutesLeft: minutes,
      art: base.id,
      source: 'goal',
      project: built.project?.title,
      lessons: built.lessons
    })
  }
  const template = '24px minmax(0,1.9fr) minmax(0,1fr) minmax(0,1fr) 56px'
  return (
    <>
      <Head title="New plan from a goal" />
      <Field icon={<MiyagiMark size={16} />} value={goal} onChange={setGoal} placeholder="I want to 3D print a stand for my phone" label="What you want to make" />
      <div className="min-h-0 overflow-y-auto" style={{ padding: '14px 24px 0' }}>
        {!base ? (
          <p className="m-0" style={{ ...meta, padding: '8px 0 4px' }}>
            {typed.trim() ? 'No plan fits that yet. Say it another way, or browse the plans.' : 'Say what you want to make. miyagi puts a plan together.'}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-[10px]">
              <div className="flex flex-wrap items-center gap-[8px]">
                <span style={meta}>Work in</span>
                {built.tools.map((p, i) => {
                  const t = tone[TOOL_TONES[i % TOOL_TONES.length]]
                  const sel = p.tool.id === chosenTool
                  return (
                    <button key={p.id} type="button" aria-pressed={sel} onClick={() => setTool(p.tool.id)} className="cursor-pointer" style={{ height: 30, padding: '0 14px', borderRadius: radius2.round, border: 0, background: t.solid, color: color.onPastel, fontSize: type2.sm, fontWeight: 500, boxShadow: sel ? `0 0 0 1.5px ${color.text}` : undefined }}>
                      {p.tool.label}
                    </button>
                  )
                })}
              </div>
              <span style={{ fontSize: type2.md, fontWeight: 600 }}>
                {built.lessons.length} lessons · {aboutHours(minutes)}
              </span>
            </div>
            <div role="table" aria-label="Lessons" style={{ marginTop: 12 }}>
              <TableHead cols={[{ label: '' }, { label: 'Lesson' }, { label: 'Grows' }, { label: 'From' }, { label: 'Time', align: 'right' }]} template={template} />
              {built.lessons.map((l, i) => (
                <TableRow key={i} template={template} height={44} label={l.title}>
                  <span style={meta}>{i + 1}</span>
                  <span className="truncate" style={{ fontWeight: 600 }}>
                    {l.title}
                  </span>
                  <span>
                    <SkillChip>{skillLabel(l.grows[0]) ?? l.grows[0]}</SkillChip>
                  </span>
                  <span className="truncate" style={meta}>
                    {l.from.title}
                  </span>
                  <span style={{ ...meta, textAlign: 'right' }}>{l.minutes} min</span>
                </TableRow>
              ))}
              {built.project && (
                <TableRow template={template} height={44} label="Project">
                  <Flag size={14} strokeWidth={1.6} style={{ color: color.label }} />
                  <span className="truncate" style={{ fontWeight: 600 }}>
                    Project · {built.project.title}
                  </span>
                  <span className="truncate" style={{ ...meta, gridColumn: 'span 2' }}>
                    {built.project.check}
                  </span>
                  <span style={{ ...meta, textAlign: 'right' }}>{built.project.minutes} min</span>
                </TableRow>
              )}
            </div>
          </>
        )}
      </div>
      <Foot note={built.from.length > 1 ? 'Built from two plans. Lessons you would not need are left out.' : base ? `Built from ${base.title}.` : ''}>
        <QuietButton label="Change it" onClick={() => setGoal('')} disabled={!goal} />
        <PrimaryButton label="Add plan" onClick={add} disabled={!base} />
      </Foot>
    </>
  )
}
