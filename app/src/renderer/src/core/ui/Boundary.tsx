/**
 * One surface's crash never blanks the whole overlay. Each island mode and overlay layer renders inside a Boundary:
 * if it throws, it renders nothing (and logs why) while everything else keeps working. It tries again on the next
 * `retryKey` change (a new mode, a new payload), so a bad message doesn't keep a surface dead.
 * (Desktop test 5: a network diagram frame without weights threw in NeuralNet and the whole overlay went blank.)
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { name: string; retryKey?: unknown; children: ReactNode }
type State = { failed: boolean; key?: unknown }

export class Boundary extends Component<Props, State> {
  state: State = { failed: false, key: this.props.retryKey }

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true }
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    // A new payload gets a fresh try.
    return props.retryKey !== state.key ? { failed: false, key: props.retryKey } : null
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[miyagi] ${this.props.name} crashed and was hidden:`, error, info.componentStack)
  }

  render(): ReactNode {
    return this.state.failed ? null : this.props.children
  }
}
