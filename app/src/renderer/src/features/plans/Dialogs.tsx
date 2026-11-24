/**
 * Feature: plans. The two "new plan" dialogs (Adrian's mocks plan-playlist and plan-goal, 23-lesson-plans-10..17).
 *
 *   From a playlist  paste a YouTube playlist link; the playlist's videos become lessons, each growing one skill, and
 *                    the plan can end with the project of the plan it matches. "Just the first video" adds one lesson.
 *   From a goal      say what you want to make; pick where you work (option chips, the one pastel use here), and the
 *                    plan is put together from the catalog's plans, ending in a project.
 *
 * Wiring (ui-v4 contract, UI-V4.md "Plans"): a pasted link sends `playlist.get {url, reqId}`; the answer comes twice
 * (the videos with proposing: true, then the same with the proposal). Add plan sends `plan.start {playlistId, url,
 * proposal}` with each unchecked video marked `skip: true` (and project null when "Ends with a project" is off).
 * The goal dialog sends `plan.propose {goal, tool, reqId}` on Enter, shows the proposing state, then draws
 * plan.proposal (lessons with from, fromPlans, minutes, note); Add plan sends `plan.start {goal, proposal}`.
 * When no engine answers within ASK_MS, the dialogs fall back to the catalog (catalog/playlists.json, planFromGoal),
 * drawn through the same PlaylistInfo / PlanProposal shapes.
 */
import { Flag, Link2, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { LookupError, PlanProposal, PlaylistInfo } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { PrimaryButton, QuietButton } from '../../core/ui/buttons'
import { MiyagiMark } from '../../core/ui/Mark'
import { color, elevation, fill, radius2, scrim, surface, tone, type Tone, type2 } from '../../core/theme'
import { aboutHours, lengthLabel, planById, playlistById, playlistIdOf, playlistInfoFromCatalog, proposalFromGoal, skillLabel } from './catalog'
import { addGoalPlan, addPlaylistPlan, closeDialog, reqId, usePlans } from './store'
import { Thumb, artFor } from './Thumb'
import { hair, meta, SkillChip, TableHead, TableRow } from './ui'

/** How long a dialog waits for the engine's first answer before it uses the catalog. */
const ASK_MS = 1500

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

function Field({ icon, value, onChange, onEnter, placeholder, label }: { icon: ReactNode; value: string; onChange: (v: string) => void; onEnter?: () => void; placeholder: string; label: string }): ReactNode {
  return (
    <label className="flex shrink-0 items-center gap-[10px]" style={{ margin: '0 24px', height: 44, padding: '0 14px', borderRadius: radius2.card, background: surface.well, boxShadow: `inset 0 0 0 1.5px ${color.text}` }}>
      <span style={{ color: color.label, display: 'flex' }}>{icon}</span>
      <input
        autoFocus
        aria-label={label}
        value={value}
        placeholder={placeholder}
        spellCheck={false}
        onChange={(e) => onChange(e.target.value.slice(0, 300))}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && onEnter) {
            e.preventDefault()
            onEnter()
          }
        }}
        className="min-w-0 flex-1"
        style={{ background: 'none', border: 0, outline: 'none', color: color.text, fontSize: type2.body }}
      />
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

/** Gray rows while the engine is still working (never a spinner that looks stuck). */
function Waiting({ rows, line }: { rows: number; line: string }): ReactNode {
  return (
    <div aria-busy aria-label={line} className="flex flex-col" style={{ gap: 8, padding: '8px 0 4px' }}>
      <span style={meta}>{line}</span>
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="block" style={{ height: 36, borderRadius: radius2.keycap, background: fill.track, opacity: 0.6 }} />
      ))}
    </div>
  )
}

const LOOKUP_LINE: Record<LookupError, string> = {
  not_found: 'miyagi couldn’t find that playlist.',
  private: 'That playlist is private.',
  unsupported: 'That doesn’t look like a playlist link.',
  offline: 'miyagi is offline. Try again when it connects.',
  too_long: 'That playlist is too long for one plan.',
  busy: 'miyagi is busy. Try again in a moment.',
  unknown: 'That didn’t work. Try again.'
}

// ---- from a playlist ------------------------------------------------------------------------------------------------

const SHOWN = 6
/** Up to two lines, then an ellipsis (a long project line wraps instead of clipping). */
const clamp2 = { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' } as const

/** playlist.get for a pasted link: the engine's answers (twice), or the catalog's playlist after ASK_MS. */
function usePlaylist(link: string): { info?: PlaylistInfo; asking: boolean } {
  const id = playlistIdOf(link)
  const url = link.trim()
  const [info, setInfo] = useState<PlaylistInfo | undefined>()
  const [asking, setAsking] = useState(false)
  useEffect(() => {
    setInfo(undefined)
    if (!id) return setAsking(false)
    const rid = reqId('pl')
    let answered = false
    setAsking(true)
    const off = onMessage('playlist', (p) => {
      if (!p || (p.reqId !== undefined && p.reqId !== rid && p.playlistId !== id) || (p.playlistId && p.playlistId !== id)) return
      answered = true
      setAsking(false)
      setInfo(p)
    })
    const timer = setTimeout(() => {
      if (answered) return
      setAsking(false)
      const local = playlistById(id)
      if (local) setInfo(playlistInfoFromCatalog(local))
    }, ASK_MS)
    bridge.send(cmd('playlist.get', { url: url.startsWith('http') ? url : `https://www.youtube.com/playlist?list=${id}`, reqId: rid }))
    return () => {
      off()
      clearTimeout(timer)
    }
    // url follows id; asking again only when the playlist changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])
  return { info, asking }
}

function PlaylistDialog(): ReactNode {
  const [link, setLink] = useState('')
  const [picked, setPicked] = useState<Record<number, boolean>>({})
  const [project, setProject] = useState(true)
  const id = playlistIdOf(link)
  const { info, asking } = usePlaylist(link)
  const proposal = info?.proposal ?? undefined
  // The plan it matches: the proposal's first source plan, else the catalog's playlist (for its picture).
  const plan = planById(proposal?.fromPlans?.[0]) ?? planById(playlistById(info?.playlistId)?.planId)
  useEffect(() => setPicked({}), [id, proposal])
  // Each video keeps its index in the playlist: unchecking one never shifts another video's skill.
  const rows = useMemo(() => (info ? info.videos.map((v, i) => ({ v, i, lesson: proposal?.lessons[i] })) : []), [info, proposal])
  const on = (i: number): boolean => picked[i] ?? !rows[i]?.lesson?.skip
  const chosen = rows.filter(({ i }) => on(i))
  const skills = new Set(chosen.flatMap((r) => r.lesson?.grows ?? [])).size
  const projectOf = proposal?.project ?? plan?.project ?? null
  const add = (first: boolean): void => {
    if (!info || !proposal || !info.playlistId) return
    const lessons = proposal.lessons.map((l, i) => ({ ...l, skip: first ? i > 0 : !on(i) }))
    const out: PlanProposal = { ...proposal, lessons, project: project && !first ? projectOf : null }
    addPlaylistPlan({ playlistId: info.playlistId, url: info.url }, out)
  }
  const template = '24px minmax(0,1fr) minmax(0,190px) 64px'
  const line = !link.trim()
    ? 'Paste the link of a YouTube playlist. Each video becomes a lesson.'
    : !id
      ? 'That doesn’t look like a playlist link.'
      : info?.error
        ? LOOKUP_LINE[info.error]
        : 'miyagi doesn’t know that playlist yet.'
  return (
    <>
      <Head title="New plan from a playlist" />
      <Field icon={<Link2 size={16} strokeWidth={1.8} />} value={link} onChange={setLink} placeholder="youtube.com/playlist?list=…" label="YouTube playlist link" />
      <div className="min-h-0 overflow-y-auto" style={{ padding: '16px 24px 0' }}>
        {asking && !info ? (
          <Waiting rows={3} line="Reading the playlist" />
        ) : !info || info.error || !info.videos.length ? (
          <p className="m-0" style={{ ...meta, padding: '8px 0 4px' }}>
            {line}
          </p>
        ) : (
          <>
            <div className="flex items-center gap-[14px]">
              <Thumb art={artFor(plan)} w={96} h={54} />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate" style={{ fontSize: type2.body, fontWeight: 600 }}>
                  {info.title}
                </span>
                <span className="truncate" style={meta}>
                  {[info.channel, `${info.videoCount ?? info.videos.length} videos`, info.totalSeconds ? lengthLabel(info.totalSeconds) : ''].filter(Boolean).join(' · ')}
                </span>
              </div>
              <div className="flex shrink-0 flex-col items-end">
                <span style={{ fontSize: type2.body, fontWeight: 600 }}>
                  {chosen.length} lessons{proposal ? ` · ${skills} skills` : ''}
                </span>
                <span style={meta}>{info.proposing ? 'Matching skills to the videos' : 'You have none of these skills yet'}</span>
              </div>
            </div>
            <div role="table" aria-label="Videos" style={{ marginTop: 16 }}>
              <TableHead cols={[{ label: '' }, { label: 'Video' }, { label: 'Becomes a lesson that grows' }, { label: 'Length', align: 'right' }]} template={template} />
              {rows.slice(0, SHOWN).map(({ v, i, lesson }) => {
                const skill = lesson?.skills?.[0] ?? (lesson?.grows?.[0] ? skillLabel(lesson.grows[0]) : undefined)
                return (
                  <TableRow key={i} template={template} height={44} label={v.title}>
                    <input type="checkbox" aria-label={`Include ${v.title}`} checked={on(i)} onChange={(e) => setPicked((p) => ({ ...p, [i]: e.target.checked }))} style={{ width: 16, height: 16, accentColor: color.text }} />
                    <span className="truncate" style={{ fontWeight: 600, opacity: on(i) ? 1 : 0.5 }}>
                      {v.title}
                    </span>
                    <span>{skill ? <SkillChip>{skill}</SkillChip> : info.proposing ? <span className="block" style={{ width: 72, height: 18, borderRadius: radius2.keycap, background: fill.track, opacity: 0.6 }} /> : null}</span>
                    <span style={{ ...meta, textAlign: 'right' }}>{v.seconds ? `${Math.round(v.seconds / 60)} min` : ''}</span>
                  </TableRow>
                )
              })}
              {info.videos.length > SHOWN && <div style={{ ...meta, padding: '12px 0 0 40px' }}>{info.videos.length - SHOWN} more videos</div>}
            </div>
            {projectOf && (
              <label className="flex cursor-pointer items-center gap-[12px]" style={{ marginTop: 16, minHeight: 44, borderTop: hair }}>
                <Flag size={15} strokeWidth={1.6} style={{ color: color.label }} />
                <span style={{ fontSize: type2.md, fontWeight: 600 }}>Ends with a project</span>
                <span className="min-w-0 flex-1 truncate" style={meta}>
                  {projectOf.title}, on your own
                </span>
                <Toggle on={project} onChange={setProject} label="Ends with a project" />
              </label>
            )}
          </>
        )}
      </div>
      <Foot note={plan ? `miyagi pauses each video until your ${plan.lessons.some((l) => l.check === 'scene') ? 'scene' : 'work'} passes the step.` : 'miyagi pauses each video until your work passes the step.'}>
        <QuietButton label="Just the first video" onClick={() => add(true)} disabled={!proposal} />
        <PrimaryButton label="Add plan" onClick={() => add(false)} disabled={!proposal || !chosen.length} />
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

type Ask = { goal: string; state: 'idle' | 'proposing' | 'done'; proposal?: PlanProposal | null; error?: LookupError }

function GoalDialog(): ReactNode {
  const [goal, setGoal] = useState('')
  const [ask, setAsk] = useState<Ask>({ goal: '', state: 'idle' })
  const live = useRef<() => void>(() => undefined)
  useEffect(() => () => live.current(), [])

  /** plan.propose {goal, tool}: proposing, then the proposal. The catalog answers when the engine doesn't. */
  const propose = (tool?: string): void => {
    const text = goal.trim()
    if (!text) return
    live.current()
    const rid = reqId('goal')
    let answered = false
    setAsk({ goal: text, state: 'proposing' })
    const off = onMessage('plan.proposal', (p) => {
      if (!p || (p.reqId !== undefined && p.reqId !== rid && p.goal !== text)) return
      answered = true
      if (p.proposing) return setAsk({ goal: text, state: 'proposing' })
      setAsk({ goal: text, state: 'done', proposal: p.proposal ?? null, error: p.error })
    })
    const timer = setTimeout(() => {
      if (!answered) setAsk({ goal: text, state: 'done', proposal: proposalFromGoal(text, tool) })
    }, ASK_MS)
    live.current = () => (off(), clearTimeout(timer))
    bridge.send(cmd('plan.propose', { goal: text, ...(tool ? { tool } : {}), reqId: rid }))
  }

  const pr = ask.state === 'done' ? (ask.proposal ?? undefined) : undefined
  const chosenTool = pr?.tool?.id
  const minutes = pr ? (pr.minutes ?? pr.lessons.reduce((n, l) => n + (l.minutes ?? 0), 0) + (pr.project ? 45 : 0)) : 0
  const add = (): void => {
    if (pr) addGoalPlan(ask.goal, pr)
  }
  const template = '24px minmax(0,1.9fr) minmax(0,1fr) minmax(0,1fr) 56px'
  const note = pr?.note ?? (pr?.fromPlans?.length ? `Built from ${pr.fromPlans.map((id) => planById(id)?.title ?? '').filter(Boolean).join(' and ')}.` : '')
  return (
    <>
      <Head title="New plan from a goal" />
      <Field icon={<MiyagiMark size={16} />} value={goal} onChange={setGoal} onEnter={() => propose()} placeholder="I want to 3D print a stand for my phone" label="What you want to make" />
      <div className="min-h-0 overflow-y-auto" style={{ padding: '14px 24px 0' }}>
        {ask.state === 'proposing' ? (
          <Waiting rows={4} line="Putting a plan together" />
        ) : !pr ? (
          <p className="m-0" style={{ ...meta, padding: '8px 0 4px' }}>
            {ask.state === 'done' ? (ask.error === 'offline' || ask.error === 'busy' ? LOOKUP_LINE[ask.error] : 'No plan fits that yet. Say it another way, or browse the plans.') : 'Say what you want to make, then press Return. miyagi puts a plan together.'}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-[10px]">
              <div className="flex flex-wrap items-center gap-[8px]">
                {(pr.tools?.length ?? 0) > 0 && <span style={meta}>Work in</span>}
                {(pr.tools ?? []).map((t, i) => {
                  const c = tone[TOOL_TONES[i % TOOL_TONES.length]]
                  const sel = t.id === chosenTool
                  return (
                    <button key={t.id} type="button" aria-pressed={sel} onClick={() => !sel && propose(t.id)} className="cursor-pointer" style={{ height: 30, padding: '0 14px', borderRadius: radius2.round, border: 0, background: c.solid, color: color.onPastel, fontSize: type2.sm, fontWeight: 500, boxShadow: sel ? `0 0 0 1.5px ${color.text}` : undefined }}>
                      {t.label}
                    </button>
                  )
                })}
              </div>
              <span style={{ fontSize: type2.md, fontWeight: 600 }}>
                {pr.lessons.filter((l) => !l.skip).length} lessons · {aboutHours(minutes)}
              </span>
            </div>
            <div role="table" aria-label="Lessons" style={{ marginTop: 12 }}>
              <TableHead cols={[{ label: '' }, { label: 'Lesson' }, { label: 'Grows' }, { label: 'From' }, { label: 'Time', align: 'right' }]} template={template} />
              {pr.lessons
                .filter((l) => !l.skip)
                .map((l, i) => {
                  const skill = l.skills?.[0] ?? (l.grows?.[0] ? skillLabel(l.grows[0]) : undefined)
                  return (
                    <TableRow key={i} template={template} height={44} label={l.title}>
                      <span style={meta}>{i + 1}</span>
                      <span className="truncate" style={{ fontWeight: 600 }}>
                        {l.title}
                      </span>
                      <span>{skill && <SkillChip>{skill}</SkillChip>}</span>
                      <span className="truncate" style={meta}>
                        {planById(l.from?.planId)?.title ?? ''}
                      </span>
                      <span style={{ ...meta, textAlign: 'right' }}>{l.minutes !== undefined ? `${l.minutes} min` : ''}</span>
                    </TableRow>
                  )
                })}
              {pr.project && (
                <TableRow template={template} height={44} label="Project">
                  <Flag size={14} strokeWidth={1.6} style={{ color: color.label }} />
                  <span style={{ fontWeight: 600, lineHeight: '18px', ...clamp2 }}>Project · {pr.project.title}</span>
                  <span style={{ ...meta, gridColumn: 'span 2', ...clamp2 }}>{pr.project.checks[0] ?? pr.project.brief}</span>
                  <span style={{ ...meta, textAlign: 'right' }}>45 min</span>
                </TableRow>
              )}
            </div>
          </>
        )}
      </div>
      <Foot note={pr ? note : ''}>
        <QuietButton
          label="Change it"
          onClick={() => {
            live.current()
            setGoal('')
            setAsk({ goal: '', state: 'idle' })
          }}
          disabled={!goal && ask.state === 'idle'}
        />
        <PrimaryButton label="Add plan" onClick={add} disabled={!pr} />
      </Foot>
    </>
  )
}
