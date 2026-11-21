/**
 * Feature: account (BUILD-PLAN A9, flag v2Cloud). Brief: app/agents/account.md
 *
 * The account window: Plan-AccountMenu, Plan-Upgrade, Plan-SignIn and Plan-Pricing, as UI on mock data. Opened with
 * openAccount(view) from core/surfaces.ts (an app window, decision 4). No network, no auth, no billing, no quota that
 * blocks a lesson. Not mounted unless v2Cloud is on (model.ts): the browser stage, or a VITE_MIYAGI_V2_CLOUD=1 build.
 *
 * Main side: src/main/features/account.ts (account:get → null until a backend exists, account:open with fixed
 * links only, account:sign-out). Stage side: ./web.ts (fixture, ?account=<view> opens the window).
 */
import { defineFeature } from '../../core/registry'
import { windowSize } from '../../core/theme'
import { AccountWindow } from './AccountWindow'
import { v2Cloud } from './model'
import './web'

export default defineFeature({
  id: 'account',
  enabled: v2Cloud,
  windows: [{ route: 'account', kind: 'app', size: windowSize.account, Component: AccountWindow }]
})
