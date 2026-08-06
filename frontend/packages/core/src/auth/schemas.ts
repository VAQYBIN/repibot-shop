import { z } from 'zod'

// Минимальная длина совпадает с политикой бэкенда: разошлись бы значения —
// форма отправляла бы заведомо отклоняемые пароли.
const password = z.string().min(10)

export const emailSchema = z.object({ email: z.string().email() })
export const passwordSchema = z.object({ password })
export const loginSchema = z.object({ email: z.string().email(), password: z.string().min(1) })
export const registerSchema = z.object({
  email: z.string().email(),
  password,
  language: z.enum(['ru', 'en']),
})
export const resetSchema = z.object({ token: z.string().min(1), password })

export type LoginInput = z.infer<typeof loginSchema>
export type RegisterInput = z.infer<typeof registerSchema>
