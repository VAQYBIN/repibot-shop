'use client'

import { Button } from '@repibot/ui'
import Link from 'next/link'

import { Lockup } from '@/components/lockup'
import { ThemeToggle } from '@/components/theme-toggle'
import { useBrowserLanguage, useTranslate } from '@/lib/i18n'

/**
 * Шапка страниц, которые видит человек до входа.
 *
 * Текстовые ссылки прячутся ниже sm, а лок-ап, переключатель темы и кнопка
 * входа остаются: без переключателя сменить тему на публичной части негде,
 * а до кабинета, где он тоже есть, ещё надо войти.
 */
export function PublicHeader() {
  const language = useBrowserLanguage()
  const t = useTranslate(language)

  return (
    <header className="border-border border-b">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 py-4">
        {/* Знак сам по себе ничего не говорит скринридеру: LogoMark скрыт от
            дерева доступности, а вордмарк читается как название, а не как
            «на главную». */}
        <Link href="/" aria-label={t('nav.home')}>
          <Lockup size={32} />
        </Link>

        <div className="flex items-center gap-2">
          {/* Ссылки в обычном div, а не в nav: шапка сама по себе ориентир,
              а второй безымянный ориентир только удлинил бы их список.

              Поддержки здесь нет намеренно: обращение заводится от аккаунта,
              и гостя с такой ссылки немедленно унесло бы на вход — обещание
              того, чего для него не существует. */}
          <div className="hidden items-center gap-4 sm:flex">
            <Link href="/plans" className="text-small text-text-secondary hover:text-text">
              {t('nav.plans')}
            </Link>
          </div>

          <ThemeToggle />

          <Button asChild size="md">
            <Link href="/login">{t('nav.login')}</Link>
          </Button>
        </div>
      </div>
    </header>
  )
}
