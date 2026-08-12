import {
  CreditCardIcon,
  Home01Icon,
  ShieldKeyIcon,
  SmartPhone01Icon,
  UserIcon,
} from '@hugeicons/core-free-icons'
import { translate } from '@repibot/core'
import { Icon } from '@repibot/ui'
import { createRootRoute, Link, Outlet } from '@tanstack/react-router'

import { useLanguage } from '../api'
import { useAuthState } from '../auth'
import { AuthFallback } from '../auth-fallback'
import { PurchaseNotice } from '../purchase-notice'

/* Пять вкладок из семи экранов: обращения и подарочные дни лесенки возврата
   не влезают без потери размера цели нажатия. Их адреса остаются рабочими —
   на них приходят по ссылкам из бота, — но панель на них не указывает. */
const TABS = [
  { to: '/', key: 'miniapp.tab.home', icon: Home01Icon },
  { to: '/subscription', key: 'miniapp.tab.subscription', icon: ShieldKeyIcon },
  { to: '/devices', key: 'miniapp.tab.devices', icon: SmartPhone01Icon },
  { to: '/payments', key: 'miniapp.tab.payments', icon: CreditCardIcon },
  { to: '/profile', key: 'miniapp.tab.profile', icon: UserIcon },
] as const

function TabBar() {
  const language = useLanguage()

  return (
    <nav
      aria-label={translate(language, 'miniapp.nav.label')}
      className="fixed inset-x-0 bottom-0 border-border-subtle border-t bg-surface pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="mx-auto flex max-w-md">
        {TABS.map((tab) => (
          <li key={tab.to} className="flex-1">
            <Link
              to={tab.to}
              activeOptions={{ exact: tab.to === '/' }}
              // Цель нажатия не меньше 44px по высоте: это нижний предел,
              // ниже которого палец промахивается мимо вкладки.
              className="flex min-h-[3.25rem] flex-col items-center justify-center gap-0.5 text-caption text-text-secondary"
              activeProps={{
                className:
                  'flex min-h-[3.25rem] flex-col items-center justify-center gap-0.5 text-caption font-medium text-text-accent',
                'aria-current': 'page',
              }}
            >
              <Icon icon={tab.icon} size={24} />
              {translate(language, tab.key)}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}

function Layout() {
  const state = useAuthState((store) => store.state)

  if (state !== 'ready') {
    return (
      <div className="min-h-dvh bg-bg p-4 text-text">
        <AuthFallback state={state} />
      </div>
    )
  }

  return (
    <div className="min-h-dvh bg-bg text-text">
      {/* Отступ снизу равен высоте панели плюс вырез экрана: без него
          последняя строка содержимого прячется под панелью. */}
      <div className="mx-auto max-w-md px-4 pt-4 pb-[calc(4.5rem+env(safe-area-inset-bottom))]">
        <Outlet />
      </div>
      {/* Не только на экране оплаты: человек возвращается из браузера на ту
          вкладку, которую выберет сам, а новость об оплате нужна на любой. */}
      <PurchaseNotice />

      <TabBar />
    </div>
  )
}

export const rootRoute = createRootRoute({ component: Layout })
