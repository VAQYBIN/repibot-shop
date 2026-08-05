import { describe, expect, it } from 'vitest'

import { loginSchema, registerSchema } from './schemas'

describe('схемы форм', () => {
  it('требует корректный адрес', () => {
    expect(loginSchema.safeParse({ email: 'не адрес', password: 'длинный пароль' }).success).toBe(
      false,
    )
  })

  it('требует пароль от десяти символов — как и бэкенд', () => {
    const result = registerSchema.safeParse({
      email: 'user@example.org',
      password: 'короткий',
      language: 'ru',
    })

    expect(result.success).toBe(false)
  })

  it('принимает валидную регистрацию', () => {
    const result = registerSchema.safeParse({
      email: 'user@example.org',
      password: 'совершенно обычный пароль',
      language: 'ru',
    })

    expect(result.success).toBe(true)
  })
})
