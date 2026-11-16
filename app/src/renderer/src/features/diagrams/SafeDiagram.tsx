/**
 * A diagram that throws while rendering must never take the overlay down with it (Michael's Mac, Sun 2:55 AM:
 * NeuralNet read samples[-1] when the rAF clock started a few ms negative, and the whole overlay unmounted).
 * Renders nothing for that diagram instead, and tries again when a new diagram arrives.
 */
import { Component, type ReactNode } from 'react'

type Props = { children: ReactNode; resetKey?: unknown }
type State = { failed: boolean; key?: unknown }

export class SafeDiagram extends Component<Props, State> {
  state: State = { failed: false, key: this.props.resetKey }

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true }
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.key ? { failed: false, key: props.resetKey } : null
  }

  componentDidCatch(error: unknown): void {
    console.error('[diagram] render failed; hidden instead of crashing the overlay', error)
  }

  render(): ReactNode {
    return this.state.failed ? null : this.props.children
  }
}
