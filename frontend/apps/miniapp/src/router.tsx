import { createRouter } from '@tanstack/react-router'

import { indexRoute } from './routes/index'
import { profileRoute } from './routes/profile'
import { rootRoute } from './routes/root'

export const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute, profileRoute]),
  basepath: '/app',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
