/**
 * One surface's crash never blanks the whole overlay. Each island mode and overlay layer renders inside a Boundary:
 * if it throws, it renders nothing (and logs why) while everything else keeps working. It tries again on the next
 * `retryKey` change (a new mode, a new payload), so a bad message doesn't keep a surface dead.
 * (Desktop test 5: a network diagram frame without weights threw in NeuralNet and the whole overlay went blank.)
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'

/** retryMs: also try again by itself after this long (the island: one bad render must not leave the screen empty). */
type Props = { name: string; retryKey?: unknown; retryMs?: number; children: ReactNode }
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

  private retry?: ReturnType<typeof setTimeout>

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[miyagi] ${this.props.name} crashed and was hidden:`, error, info.componentStack)
    const ms = this.props.retryMs
    if (ms != null) {
      clearTimeout(this.retry)
      // A fresh mount: a stale hot reload ("calling Hooks conditionally") recovers on a clean first render.
      this.retry = setTimeout(() => this.setState({ failed: false }), ms)
    }
  }

  componentWillUnmount(): void {
    clearTimeout(this.retry)
  }

  render(): ReactNode {
    return this.state.failed ? null : this.props.children
  }
}
