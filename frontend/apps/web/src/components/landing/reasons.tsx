import { BubbleChatIcon, CreditCardIcon, GiftIcon, Link01Icon } from '@hugeicons/core-free-icons'
import { type TranslationKey, translate } from '@repibot/core'
import { Icon, type IconSvgElement } from '@repibot/ui'

interface Reason {
  icon: IconSvgElement
  title: TranslationKey
  text: TranslationKey
}

/**
 * Четыре довода в том порядке, в каком человек о них вспоминает: сначала
 * «сколько это стоит попробовать», потом «как этим пользоваться», потом
 * «чем платить» и лишь затем «что будет, если сломается».
 */
const REASONS: readonly Reason[] = [
  { icon: GiftIcon, title: 'landing.reason.trial.title', text: 'landing.reason.trial.text' },
  { icon: Link01Icon, title: 'landing.reason.link.title', text: 'landing.reason.link.text' },
  {
    icon: CreditCardIcon,
    title: 'landing.reason.payment.title',
    text: 'landing.reason.payment.text',
  },
  {
    icon: BubbleChatIcon,
    title: 'landing.reason.support.title',
    text: 'landing.reason.support.text',
  },
]

/**
 * Доводы.
 *
 * Своего заголовка у раздела нет намеренно: он продолжает первый экран, и
 * второй заголовок между обещанием и его расшифровкой только разорвал бы их.
 *
 * Ни рамок, ни подложек: четыре одинаковые карточки в ряд — заготовка, а не
 * решение, и вес они дали бы одинаковый всем четырём доводам сразу. Иконка
 * стоит в строке заголовка и декоративна — та же мысль рядом словами.
 *
 * Зелёный на иконках, а не на подложке под ними: Jade маркирует принадлежность
 * бренду, и четыре залитых плашки спорили бы за внимание с единственной
 * акцентной кнопкой первого экрана.
 */
export function LandingReasons() {
  return (
    <section className="grid grid-cols-1 gap-x-10 gap-y-10 md:grid-cols-2">
      {REASONS.map((reason) => (
        <div key={reason.title} className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <Icon icon={reason.icon} size={24} className="shrink-0 text-text-accent" />
            <h3 className="font-semibold text-h3 text-text">{translate('ru', reason.title)}</h3>
          </div>
          <p className="max-w-[46ch] text-body text-text-secondary">
            {translate('ru', reason.text)}
          </p>
        </div>
      ))}
    </section>
  )
}
