import { type Language, type TranslationKey, translate } from '../i18n/index'

/** Код ошибки бэкенда → ключ словаря. Незнакомый код не должен давать пустоту. */
export function errorMessageKey(code: string | undefined): TranslationKey {
  const known: Record<string, TranslationKey> = {
    invalid_credentials: 'auth.error.invalid_credentials',
    email_not_verified: 'auth.error.email_not_verified',
    email_taken: 'auth.error.email_taken',
    weak_password: 'auth.error.weak_password',
    token_invalid: 'auth.error.token_invalid',
    rate_limited: 'auth.error.rate_limited',
    // Проверка данных на бэкенде строже клиентской: скажем, зарезервированные
    // домены вроде example.test он отвергает. Без этой строки человек видел бы
    // «не удалось выполнить запрос» и не понимал, что не так с адресом.
    validation_error: 'auth.error.validation_error',
    last_login_method: 'auth.error.last_login_method',
    link_conflict: 'auth.error.link_conflict',
    telegram_already_linked: 'auth.error.telegram_already_linked',
    // Приходит не телом ответа, а параметром ?error= после возврата из
    // Telegram: браузерный вход отвечает редиректами, включая отказы.
    telegram_unavailable: 'auth.error.telegram_unavailable',
    // Тем же путём на страницу входа попадает отказ заблокированному аккаунту.
    // Без строки человек видел бы «не удалось выполнить запрос» и повторял
    // попытку, которая не пройдёт никогда.
    forbidden: 'auth.error.forbidden',
    // Удалённый ключ, отозванная сессия, снятая привязка: список на экране
    // устарел, и перезагрузка страницы — то, что человеку нужно сделать.
    not_found: 'auth.error.not_found',
    panel_unavailable: 'error.panel_unavailable',
    device_not_found: 'error.device_not_found',
    subscription_missing: 'error.subscription_missing',
    trial_already_used: 'error.trial_already_used',
    trial_requires_telegram: 'error.trial_requires_telegram',
    trial_disabled: 'error.trial_disabled',
    subscription_exists: 'error.subscription_exists',
    subscription_not_found: 'payment.error.subscription_not_found',
    provider_unavailable: 'payment.error.provider_unavailable',
    telegram_required: 'payment.error.telegram_required',
    order_expired: 'payment.error.order_expired',
    plan_inactive: 'payment.error.plan_inactive',
    plan_not_found: 'payment.error.plan_not_found',
    promo_unavailable: 'payment.error.promo_unavailable',
    gift_unavailable: 'payment.error.gift_unavailable',
    payment_not_verified: 'payment.error.payment_not_verified',
    auto_renew_unavailable: 'payment.auto_renew.unavailable',
  }
  return (code && known[code]) || 'auth.error.unknown'
}

export function messageFrom(error: unknown, language: Language): string {
  const code = (error as { error?: { code?: string } })?.error?.code
  return translate(language, errorMessageKey(code))
}
