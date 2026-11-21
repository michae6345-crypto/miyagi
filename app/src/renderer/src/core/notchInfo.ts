/**
 * The notch layout as the last layout message said it (main re-sends it when displays change or Boring Notch starts or
 * quits), for surfaces that have no `layout` prop of their own (Settings > General). The browser stage has it from the start.
 */
import { create } from 'zustand'
import type { NotchLayout } from '../../../common/notch'
import { isElectron, STAGE } from '../bridge'

export const useNotchInfo = create<{ notch?: NotchLayout }>(() => ({ notch: isElectron ? undefined : STAGE.notch }))

export const setNotchInfo = (notch: NotchLayout | undefined): void => useNotchInfo.setState({ notch })
