# app-onscreen-coach

**Status:** claimed (Nov 24), coding next · **Port:** 5205 · **Branch:** `michael/app-onscreen-coach`

## Goal
In an app lesson (lesson.app: Blender, AutoCAD...), the buddy circles the target on screen and writes the step's
action (plus its keycaps) right beside the circle. The lesson drawer starts collapsed to the island; the steps list
stays one click away.

## Owns
- `app/src/renderer/src/features/annotate/**` (text beside the loop, text-mark hold rule, drawer collapse)
- `app/mock/scenarios/onscreen.json`
- `app/agents/app-onscreen-coach.md`, `app/agents/shots/app-onscreen-coach-*.png`, ports.json entry

## Core requests
- (a) Merge the engine lane's contract commit (Annotation text/keys, LessonInfo.app) into v2-integration.
- (b) A core Keycap variant for an engine-given key label.
- (c) Optional: `useLessonApp()` in core/lesson.
