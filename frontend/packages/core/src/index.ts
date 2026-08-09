export { createApiClient } from './api/client'
export { type AuthClientOptions, createAuthClient } from './auth/client'
export { errorMessageKey } from './auth/errors'
export {
  AuthProvider,
  type AuthProviderProps,
  useAuthClient,
  useLogin,
  useLogout,
  useMe,
  useRegister,
  useRequestEmailChange,
  useRevokeSession,
  useSessions,
  useUpdateProfile,
} from './auth/hooks'
export {
  emailSchema,
  type LoginInput,
  loginSchema,
  passwordSchema,
  type RegisterInput,
  registerSchema,
  resetSchema,
} from './auth/schemas'
export { createTokenStore, type TokenStore } from './auth/store'
export {
  detectLanguage,
  en,
  type Language,
  ru,
  type TranslationKey,
  translate,
} from './i18n/index'
export { createQueryClient } from './query'
export { formatBytes, formatDate } from './subscription/format'
export {
  useActivateTrial,
  useDevices,
  usePlans,
  useSubscription,
  useTraffic,
  useUnlinkDevice,
} from './subscription/hooks'
