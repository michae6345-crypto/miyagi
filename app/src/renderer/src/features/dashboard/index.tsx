/**
 * Feature: dashboard. Brief: app/agents/dashboard.md · research: miyagi-v2/DASHBOARD-RESEARCH.md
 *
 * The lesson dashboard with the skill constellation. It has no window of its own: it is Library's Home section (the
 * default view, so the Dock click and the tray's openLibrary() land on it) and the Progress window's body.
 * Stage: ?scenario=dashboard&window=library&size=1440x900&clean  ·  &window=progress
 */
import { defineFeature } from '../../core/registry'

export default defineFeature({ id: 'dashboard' })
