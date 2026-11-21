import { createContext, useContext } from 'react'

/** True inside the island's content while it is drawn in the notch (core/Island.tsx): a mode can drop a mark the ears already show. */
export const NotchContext = createContext(false)
export const useInNotch = (): boolean => useContext(NotchContext)
