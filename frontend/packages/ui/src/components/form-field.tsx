import { Children, cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react'

import { cn } from '../lib/cn'

interface FieldAria {
  'aria-describedby'?: string
  'aria-invalid'?: boolean
}

export interface FormFieldProps {
  label: string
  /** Совпадает с `id` вложенного поля: подпись связывается с ним через `htmlFor`. */
  htmlFor: string
  hint?: string | undefined
  error?: string | null | undefined
  children: ReactNode
  className?: string | undefined
}

/**
 * Подпись, поле, подсказка и ошибка как одно целое.
 *
 * Поле приходит извне готовым элементом, поэтому aria-атрибуты дописываются
 * клонированием: иначе каждый вызов повторял бы `aria-describedby` руками, а
 * забытый атрибут означает, что скринридер не прочитает причину отказа.
 */
function withAria(children: ReactNode, aria: FieldAria): ReactNode {
  if (Children.count(children) !== 1) return children
  const only = Children.toArray(children)[0]
  if (only === undefined || !isValidElement<FieldAria>(only)) return children
  return cloneElement(only as ReactElement<FieldAria>, aria)
}

export function FormField({ label, htmlFor, hint, error, children, className }: FormFieldProps) {
  const hintId = `${htmlFor}-hint`
  const errorId = `${htmlFor}-error`
  const described = [hint ? hintId : null, error ? errorId : null].filter(
    (value): value is string => value !== null,
  )

  const aria: FieldAria = {}
  if (described.length > 0) aria['aria-describedby'] = described.join(' ')
  if (error) aria['aria-invalid'] = true

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={htmlFor} className="text-small font-medium text-text">
        {label}
      </label>
      {withAria(children, aria)}
      {hint ? (
        <p id={hintId} className="text-small text-text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-small text-danger">
          {error}
        </p>
      ) : null}
    </div>
  )
}
