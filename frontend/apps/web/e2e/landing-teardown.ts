import { restoreDefaultLanding } from './landing-stack'

export default function globalTeardown(): void {
  restoreDefaultLanding()
}
