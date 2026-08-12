import { ArrowDown01Icon } from '@hugeicons/core-free-icons'
import { type TranslationKey, translate } from '@repibot/core'
import { Icon } from '@repibot/ui'

interface Question {
  question: TranslationKey
  answer: TranslationKey
}

const QUESTIONS: readonly Question[] = [
  { question: 'landing.faq.q1', answer: 'landing.faq.a1' },
  { question: 'landing.faq.q2', answer: 'landing.faq.a2' },
  { question: 'landing.faq.q3', answer: 'landing.faq.a3' },
  { question: 'landing.faq.q4', answer: 'landing.faq.a4' },
  { question: 'landing.faq.q5', answer: 'landing.faq.a5' },
  { question: 'landing.faq.q6', answer: 'landing.faq.a6' },
]

/**
 * Частые вопросы.
 *
 * `<details>` вместо своего раскрывающегося блока: он работает с клавиатуры и
 * из поиска по странице сам, не требует состояния и остаётся раскрываемым до
 * гидратации. Radix-компонента под это в `@repibot/ui` нет, и заводить её
 * ради шести пар текста не за чем.
 */
export function LandingFaq() {
  return (
    <section className="flex flex-col gap-8">
      <h2 className="font-semibold text-h2 text-text">{translate('ru', 'landing.faq.title')}</h2>

      <div className="flex flex-col border-border-subtle border-t">
        {QUESTIONS.map((item) => (
          <details key={item.question} className="group border-border-subtle border-b">
            {/* Своя стрелка вместо системного треугольника, поэтому маркер
                гасится дважды: `list-none` понимает Firefox, псевдоэлемент —
                Safari и остальные webkit-браузеры. */}
            <summary className="flex cursor-pointer list-none items-start justify-between gap-4 py-5 font-medium text-body text-text hover:text-text-accent [&::-webkit-details-marker]:hidden">
              {translate('ru', item.question)}
              {/* Стрелка сообщает то же, что и состояние самого `<details>`,
                  поэтому от скринридера скрыта: он и так читает «свёрнуто».
                  Поворот — единственное движение на странице, и оно отвечает
                  на нажатие, а не украшает прокрутку. */}
              <Icon
                icon={ArrowDown01Icon}
                size={20}
                className="mt-0.5 shrink-0 text-text-muted transition-transform group-open:rotate-180"
              />
            </summary>
            <p className="max-w-[70ch] pb-6 text-body text-text-secondary">
              {translate('ru', item.answer)}
            </p>
          </details>
        ))}
      </div>
    </section>
  )
}
