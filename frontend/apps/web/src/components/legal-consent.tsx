'use client'

import { useLegalDocuments } from '@repibot/core'
import Link from 'next/link'
import { Fragment } from 'react'

import { useBrowserLanguage, useTranslate } from '@/lib/i18n'

/** Запятая между документами, союз перед последним, ничего перед первым. */
function separator(index: number, total: number, and: string): string {
  if (index === 0) return ''
  return index === total - 1 ? ` ${and} ` : ', '
}

/**
 * Согласие с документами под кнопкой регистрации.
 *
 * Галочки нет намеренно: согласие выражается действием, а обязательная галочка
 * добавляет шаг и ничего не добавляет к доказательству — факт создания аккаунта
 * фиксирует и то и другое одинаково.
 *
 * Пустой список и неудачный запрос неразличимы: ссылаться не на что, а фраза
 * про принятие документов без самих документов обещает то, чего нет.
 */
export function LegalConsent() {
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const legal = useLegalDocuments(language)

  const documents = legal.data ?? []
  if (documents.length === 0) return null

  const and = t('consent.and')

  return (
    <p className="mt-4 text-caption text-text-muted">
      {t('consent.before')}{' '}
      {documents.map((document, index) => (
        <Fragment key={document.slug}>
          {separator(index, documents.length, and)}
          <Link href={`/legal/${document.slug}`} className="text-text-accent hover:underline">
            {document.title}
          </Link>
        </Fragment>
      ))}
      .
    </p>
  )
}
