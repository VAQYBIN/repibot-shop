'use client'

import { useLegalDocuments } from '@repibot/core'
import Link from 'next/link'

import { Lockup } from '@/components/lockup'
import { useBrowserLanguage, useTranslate } from '@/lib/i18n'

const SECTIONS = [
  { href: '/plans', key: 'nav.plans' },
  { href: '/login', key: 'nav.login' },
  { href: '/register', key: 'nav.register' },
] as const

/**
 * Подвал публичных страниц.
 *
 * Правовая колонка приходит из API и потому появляется не сразу — остальной
 * подвал от этого запроса не зависит намеренно: недоступный бэкенд не должен
 * уносить навигацию вместе с собой.
 */
export function PublicFooter() {
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const legal = useLegalDocuments(language)

  // Пустой раздел «Правовая информация» с нулём ссылок хуже его отсутствия,
  // а неудачный запрос ничем не отличается от «документов не завели»:
  // и в том и в другом случае показывать нечего.
  const documents = legal.data ?? []

  return (
    <footer className="border-border-subtle border-t">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-6 py-10">
        <div className="flex flex-col gap-8 sm:flex-row sm:justify-between">
          <div className="flex flex-col gap-3">
            <Lockup size={28} />
            <p className="max-w-xs text-small text-text-secondary">{t('footer.about')}</p>
          </div>

          <div className="flex flex-col gap-8 sm:flex-row sm:gap-16">
            <nav aria-label={t('footer.sections')} className="flex flex-col gap-2">
              <h2 className="font-medium text-caption text-text-muted uppercase">
                {t('footer.sections')}
              </h2>
              {SECTIONS.map((section) => (
                <Link
                  key={section.href}
                  href={section.href}
                  className="text-small text-text-secondary hover:text-text"
                >
                  {t(section.key)}
                </Link>
              ))}
            </nav>

            {documents.length === 0 ? null : (
              <nav aria-label={t('footer.legal')} className="flex flex-col gap-2">
                <h2 className="font-medium text-caption text-text-muted uppercase">
                  {t('footer.legal')}
                </h2>
                {documents.map((document) => (
                  <Link
                    key={document.slug}
                    href={`/legal/${document.slug}`}
                    className="text-small text-text-secondary hover:text-text"
                  >
                    {document.title}
                  </Link>
                ))}
              </nav>
            )}
          </div>
        </div>

        <p className="text-caption text-text-muted">
          © {new Date().getFullYear()} Re:Pibot. {t('footer.rights')}
        </p>
      </div>
    </footer>
  )
}
