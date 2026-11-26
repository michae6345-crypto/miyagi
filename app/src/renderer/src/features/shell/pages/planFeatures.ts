/**
 * Feature: shell. What each plan includes, as the Account page's plan card lists it. Content, not UI: edit the words
 * here. Numbers come from the catalog (features/account) when it has them, so nothing here can drift from the price
 * sheet. Generic on purpose: nothing about a particular lesson.
 */
import type { Catalog, PlanId } from '../../account/model'

export function planFeatures(plan: PlanId, catalog?: Catalog): string[] {
  const help = plan === 'free' ? catalog?.free?.help : catalog?.pro?.help
  const common = ['Lessons from a goal or a YouTube link', 'Checks never count against your help']
  if (plan === 'free') return [...common, help ? `${help} live helps a month` : 'A monthly allowance of live help', 'Your own key, any time']
  return [...common, help ? `${help} live helps a month` : 'More live help every month', 'Progress synced across your computers']
}
