import { translate } from '@repibot/core'
import { Button, LogoMark } from '@repibot/ui'
import Link from 'next/link'

/**
 * Первый экран лендинга.
 *
 * Главная кнопка зависит от данных, а не от текста: обещать пробный период,
 * когда администратор его выключил, — способ привести человека к форме
 * регистрации и там же его разочаровать. Ровно ради этой развилки тарифы
 * забираются живыми.
 *
 * Вторая кнопка стоит только рядом с пробным периодом. Без него обе вели бы на
 * `/plans` — два соседних действия с одним адресом и разными подписями заставят
 * выбирать там, где выбора нет.
 *
 * Подписи берутся вызовом `translate('ru', …)`: первый кадр всегда русский,
 * как и `lang` в корневой разметке, — язык браузера подставляется после
 * гидратации и только в клиентских частях.
 */
export function LandingHero({ hasTrial }: { hasTrial: boolean }) {
  return (
    <section className="flex flex-col gap-10 md:flex-row md:items-center md:justify-between md:gap-12">
      <div className="flex flex-col items-start gap-6">
        {/* Кегль меняется ступенью шкалы, а не своим размером: 48 px на узком
            экране съедают первый экран целиком. */}
        <h1 className="max-w-[24ch] text-balance font-semibold text-h1 text-text sm:text-display">
          {translate('ru', 'landing.hero.title')}
        </h1>
        <p className="max-w-[46ch] text-h3 text-text-secondary">
          {translate('ru', 'landing.hero.subtitle')}
        </p>

        <div className="flex flex-wrap gap-3">
          {hasTrial ? (
            <>
              <Button asChild size="lg">
                <Link href="/register">{translate('ru', 'landing.hero.cta_trial')}</Link>
              </Button>
              <Button asChild size="lg" variant="secondary">
                <Link href="/plans">{translate('ru', 'landing.hero.secondary')}</Link>
              </Button>
            </>
          ) : (
            <Button asChild size="lg">
              <Link href="/plans">{translate('ru', 'landing.hero.cta_plans')}</Link>
            </Button>
          )}
        </div>
      </div>

      {/* Знак декоративен: назван он уже в шапке, и второе «Re:Pibot» подряд
          скринридер прочитал бы как ещё одну ссылку на главную. Отступ `p-8` —
          охранное поле из раздела 4 бренд-бука: полтора диаметра ядра при
          высоте 112 px это 28 px, и края макета в них не заходят. Ниже md знак
          убран совсем — там первый экран нужен целиком под обещание. */}
      <div className="hidden shrink-0 p-8 md:block">
        <LogoMark aria-hidden="true" className="h-28 w-auto text-text" />
      </div>
    </section>
  )
}
