export class ApiError extends Error {
  /** @param {number} status @param {string} code @param {string} [message] @param {any} [data] */
  constructor(status, code, message, data) {
    super(message || code)
    this.status = status
    this.code = code
    this.data = data
  }
}

/** Map an error to a Persian/English message via i18n key errors.<code>. */
export function errorMessage(err, t) {
  const code = err?.code || 'unknown'
  const key = `errors.${code}`
  const msg = t(key)
  return msg === key ? t('errors.unknown') : msg
}
