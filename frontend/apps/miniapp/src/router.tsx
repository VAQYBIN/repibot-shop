import { createRouter } from '@tanstack/react-router'

import { devicesRoute } from './routes/devices'
import { indexRoute } from './routes/index'
import { paymentsRoute } from './routes/payments'
import { profileRoute } from './routes/profile'
import { rootRoute } from './routes/root'
import { subscriptionRoute } from './routes/subscription'

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    indexRoute,
    subscriptionRoute,
    paymentsRoute,
    devicesRoute,
    profileRoute,
  ]),
  basepath: '/app',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
