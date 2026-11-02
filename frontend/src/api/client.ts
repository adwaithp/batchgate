const TOKEN_KEY = 'batchgate.token'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: (): string | null => {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set: (token: string) => {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      /* storage unavailable: session lasts until reload */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* ignore */
    }
  },
}

/** Called when the API says the session is no longer valid. Set by the auth store. */
let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let res: Response
  try {
    res = await fetch(`/api${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the BatchGate server. Check that the API is running.')
  }

  if (res.status === 401 && token) onUnauthorized()

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  return res
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await send(path, init)).json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, json('POST', body)),
  put: <T>(path: string, body: unknown) => request<T>(path, json('PUT', body)),
  postForm: <T>(path: string, data: Record<string, string>) =>
    request<T>(path, { method: 'POST', body: new URLSearchParams(data) }),
  /**
   * Follow a server-sent event stream. Uses fetch rather than EventSource so the auth header
   * goes along. Return true from onEvent to stop listening; pass init.signal to abort.
   */
  async stream<E>(path: string, init: RequestInit, onEvent: (event: E) => boolean | void) {
    const res = await send(path, init)
    const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader()
    let buffer = ''
    try {
      for (;;) {
        const { value, done } = await reader.read()
        if (done) return
        buffer += value
        let end: number
        while ((end = buffer.indexOf('\n\n')) >= 0) {
          const data = buffer
            .slice(0, end)
            .split('\n')
            .filter((line) => line.startsWith('data: '))
            .map((line) => line.slice(6))
            .join('\n')
          buffer = buffer.slice(end + 2)
          if (data && onEvent(JSON.parse(data) as E) === true) return
        }
      }
    } finally {
      reader.cancel().catch(() => {})
    }
  },
  /** Fetch a protected file and open it in a new tab (links can't send the auth header). */
  async openFile(path: string) {
    const token = tokenStore.get()
    const res = await fetch(`/api${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new ApiError(res.status, 'Could not open the file.')
    const url = URL.createObjectURL(await res.blob())
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  },
}
