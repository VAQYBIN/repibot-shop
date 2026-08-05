import { createRootRoute, Outlet } from '@tanstack/react-router'

export const rootRoute = createRootRoute({
  component: () => (
    <div className="min-h-dvh bg-bg p-4 text-text">
      <Outlet />
    </div>
  ),
})
