import { createRouter } from '@tanstack/react-router'

import { indexRoute } from './routes/index'
import { rootRoute } from './routes/root'

export const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute]),
  basepath: '/app',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
