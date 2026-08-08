import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'

// Даже если рендер упал до React cleanup, глобальные HTTP/browser doubles не
// переходят в следующий тест и не делают результат зависимым от порядка.
afterEach(() => vi.unstubAllGlobals())

/**
 * Язык интерфейса до входа берётся из настроек браузера, а jsdom сообщает
 * en-US. Тесты сверяют русские подписи, поэтому предпочтения фиксируются
 * здесь один раз, а не в каждом файле.
 */
Object.defineProperty(window.navigator, 'languages', {
  value: ['ru-RU', 'ru'],
  configurable: true,
})
Object.defineProperty(window.navigator, 'language', {
  value: 'ru-RU',
  configurable: true,
})
