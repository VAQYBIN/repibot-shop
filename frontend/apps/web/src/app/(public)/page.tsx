import { LandingFaq } from '@/components/landing/faq'
import { LandingHero } from '@/components/landing/hero'
import { LandingPlans, type PublicPlan } from '@/components/landing/plans-section'
import { LandingReasons } from '@/components/landing/reasons'
import { LandingSteps } from '@/components/landing/steps'
import { fetchFromApi } from '@/lib/server-api'

/**
 * Главная.
 *
 * Тарифы забираются на сервере: цена, не попавшая в HTML, не попадёт ни в
 * выдачу поисковика, ни в превью ссылки — а это два места, где страницу
 * впервые видят.
 *
 * Переключателя темы здесь нет: он живёт в шапке публичной оболочки, и второй
 * такой же на странице спорил бы с ним и за внимание, и за поиск по имени.
 */
export default async function HomePage() {
  const plans = await fetchFromApi<PublicPlan[]>('/api/plans')

  // Недоступный API — не повод обещать пробный период: `null` означает «не
  // знаем», и кнопка честно уводит на список тарифов.
  const hasTrial = (plans ?? []).some((plan) => plan.is_trial)

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-20 px-6 py-16 sm:gap-24 sm:py-24">
      <LandingHero hasTrial={hasTrial} />
      <LandingReasons />
      <LandingSteps />
      <LandingPlans plans={plans} />
      <LandingFaq />
    </main>
  )
}
