/**
 * Запросы к API из серверных компонентов.
 *
 * В браузере базовый адрес относительный: веб и API стоят за одним nginx.
 * На сервере относительный путь разрешать не от чего, поэтому нужен
 * внутренний адрес контейнера — он и приходит переменной окружения.
 *
 * Ошибка возвращается как `null`, а не бросается: главная и страница
 * документа обязаны открываться, даже когда магазин временно не работает.
 * Пятисотка на витрине из-за недоступного бэкенда — худший из возможных
 * ответов посетителю.
 */

const DEFAULT_API_URL = 'http://api:8000'

/** Цена тарифа меняется раз в месяц, а главную открывают чаще. */
const DEFAULT_REVALIDATE_SECONDS = 60

export async function fetchFromApi<T>(
  path: string,
  options: { revalidate?: number } = {},
): Promise<T | null> {
  const base = process.env.INTERNAL_API_URL ?? DEFAULT_API_URL

  try {
    const response = await fetch(`${base}${path}`, {
      next: { revalidate: options.revalidate ?? DEFAULT_REVALIDATE_SECONDS },
    })
    if (!response.ok) return null
    return (await response.json()) as T
  } catch {
    return null
  }
}
