/**
 * Чтение письма из Mailpit.
 *
 * Сквозной тест обязан пройти тем же путём, что человек: получить письмо и
 * открыть ссылку. Достать токен из базы было бы проще и проверяло бы не то —
 * доставка писем ломается чаще, чем запись в таблицу.
 */

interface MailpitSearch {
  messages: { ID: string }[]
}

interface MailpitMessage {
  Text: string
}

/**
 * Ждёт письмо получателю и возвращает первую подходящую под шаблон ссылку.
 *
 * Просматриваются все письма адресата, а не только последнее: к моменту сброса
 * пароля в ящике уже лежит письмо подтверждения, и разбор одного верхнего
 * сообщения зависел бы от порядка выдачи.
 */
export async function waitForLink(
  mailpitUrl: string,
  recipient: string,
  pattern: RegExp,
  timeoutMs = 30_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs
  let lastError: unknown = null

  while (Date.now() < deadline) {
    try {
      const query = encodeURIComponent(`to:${recipient}`)
      const found = await search(mailpitUrl, query, pattern)
      if (found !== null) return found
    } catch (error) {
      // Mailpit мог ещё не открыть порт: пробуем снова до истечения срока.
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }

  const reason = lastError === null ? '' : ` (последняя ошибка: ${String(lastError)})`
  throw new Error(`письмо для ${recipient} не пришло за ${timeoutMs} мс${reason}`)
}

async function search(mailpitUrl: string, query: string, pattern: RegExp): Promise<string | null> {
  const response = await fetch(`${mailpitUrl}/api/v1/search?query=${query}`)
  if (!response.ok) throw new Error(`Mailpit ответил ${response.status}`)
  const body = (await response.json()) as MailpitSearch

  for (const message of body.messages) {
    const details = await fetch(`${mailpitUrl}/api/v1/message/${message.ID}`)
    if (!details.ok) continue
    const { Text } = (await details.json()) as MailpitMessage
    const match = Text.match(pattern)
    if (match) return match[0]
  }

  return null
}
