import { translate } from '@repibot/core'
import Link from 'next/link'

import { type Plan, PlanCard } from '@/components/plan-card'

/**
 * Форма ответа `GET /api/plans`.
 *
 * Своего описания поля в поле она не заводит: карточка тарифа уже объявила
 * ровно эту форму, и две копии одной структуры разошлись бы на первом же
 * новом поле в API.
 */
export type PublicPlan = Plan

/**
 * Тарифы на главной.
 *
 * Пробный тариф из карточек убран: он уже обещан кнопкой первого экрана, и
 * карточка с нулевой ценой рядом с платными сбивает сравнение.
 *
 * `null` означает, что API не ответил. Страница при этом обязана открыться —
 * место карточек занимает честная строка и ссылка на полный список, а не
 * пятисотка.
 */
export function LandingPlans({ plans }: { plans: PublicPlan[] | null }) {
  const sellable = plans === null ? [] : plans.filter((plan) => !plan.is_trial)

  return (
    <section className="flex flex-col gap-8">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h2 className="font-semibold text-h2 text-text">
          {translate('ru', 'landing.plans.title')}
        </h2>
        {/* Ссылка, а не вторая кнопка: акцентная кнопка на экране одна, и она
            уже стоит на первом. */}
        <Link href="/plans" className="text-small text-text-accent hover:underline">
          {translate('ru', 'landing.plans.all')}
        </Link>
      </div>

      {plans === null ? (
        <p className="text-body text-text-secondary">
          {translate('ru', 'landing.plans.unavailable')}
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {sellable.map((plan) => (
            <li key={plan.id}>
              {/* Русский первый кадр: язык браузера подставляется после
                  гидратации, а сюда цена обязана попасть уже на сервере. */}
              <PlanCard plan={plan} language="ru" />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
