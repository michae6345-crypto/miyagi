# onboarding (A3)

**Status:** in progress · **Priority:** P0 (first run) · **Port:** 5188 · **Branch:** `michael/app-onboarding`

## Goal
First run, one window: the four things miyagi needs (Screen Recording, Accessibility, the VS Code companion, the engine
with its cloud access) as rows that update on their own, then "You're all set" and Start learning. Mid-lesson, when a
permission goes away, a recovery card grows out of the pill, keeps the learner's place, and goes away once it is back.

## Owns (BUILD-PLAN A3)
- `app/src/renderer/src/features/onboarding/**`
- `app/src/main/features/onboarding.ts`
- `app/mock/scenarios/onboarding.json`
- `app/agents/onboarding.md`

## Mockups
Onb-Setup-Full, Onb-Checklist-Mixed, Onb-Setup-Ready, Onb-Permission-Recovery.

## Test
`npm run dev:web -- --port 5188` → `http://localhost:5188/?scenario=onboarding&onb=full|mixed|ready|recovery&size=1440x900&clean`

## Core requests
_None yet._
