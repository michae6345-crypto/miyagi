/**
 * Feature: ambient. Settings > General, "Help outside lessons": the "Offer help with errors" switch (on by default) and
 * the apps miyagi never watches (muted from an error card's "Not in <app>", unmuted here). Spotting is local: the
 * caption says nothing leaves the Mac until Explain. Drawn with the settings feature's own Group / Row, so it matches.
 */
import type { ReactNode } from 'react'
import { QuietButton, Toggle } from '../../core/ui/atoms'
import { Group, Row } from '../settings/ui'
import { setOfferErrors, unmuteApp, useAmbientPrefs } from './prefs'

export function AmbientSettings(): ReactNode {
  const errors = useAmbientPrefs((s) => s.errors)
  const muted = useAmbientPrefs((s) => s.mutedApps)
  return (
    <Group label="Help outside lessons">
      <div data-settings-ambient>
        <Row
          tight
          label="Offer help with errors"
          caption="Read on this Mac. Nothing is sent until you press Explain."
          right={<Toggle label="Offer help with errors" on={errors} onChange={setOfferErrors} />}
        />
      </div>
      {muted.length ? (
        muted.map((app) => (
          <div key={app} data-settings-muted={app}>
            <Row tight label={app} caption="Never watched for errors." right={<QuietButton label="Unmute" onClick={() => unmuteApp(app)} />} />
          </div>
        ))
      ) : (
        <div data-settings-muted="">
          <Row tight label="Muted apps" caption={'None yet. Mute one from its error card.'} />
        </div>
      )}
    </Group>
  )
}
