import { type TranslationKey, translate } from '@repibot/core'

interface Step {
  title: TranslationKey
  text: TranslationKey
}

const STEPS: readonly Step[] = [
  { title: 'landing.step.account.title', text: 'landing.step.account.text' },
  { title: 'landing.step.plan.title', text: 'landing.step.plan.text' },
  { title: 'landing.step.connect.title', text: 'landing.step.connect.text' },
]

/**
 * «Как это работает» — три шага.
 *
 * Нумерованный список, а не три карточки: порядок здесь и есть содержание.
 *
 * Номер рисуется своим элементом, а не маркером `list-decimal`: маркер не
 * покрасить и не обвести. От скринридера он при этом не скрыт — сброс стилей
 * гасит `list-style`, а вместе с ним Safari теряет и семантику списка, так что
 * произнесённый номер остаётся единственным, кто сообщает порядок.
 */
export function LandingSteps() {
  return (
    <section className="flex flex-col gap-8">
      <h2 className="font-semibold text-h2 text-text">{translate('ru', 'landing.steps.title')}</h2>

      <ol className="grid grid-cols-1 gap-x-10 gap-y-8 md:grid-cols-3">
        {STEPS.map((step, index) => (
          <li key={step.title} className="flex flex-col gap-2">
            <span className="flex size-8 items-center justify-center rounded-full border border-border-subtle font-medium text-caption text-text-secondary tabular-nums">
              {index + 1}
            </span>
            <h3 className="mt-1 font-semibold text-h3 text-text">{translate('ru', step.title)}</h3>
            <p className="max-w-[42ch] text-body text-text-secondary">
              {translate('ru', step.text)}
            </p>
          </li>
        ))}
      </ol>
    </section>
  )
}
