const env = import.meta.env || {}
const apiBase = normalizeBase(env.VITE_API_URL || '/api')
const configuredWsUrl = (env.VITE_WS_URL || '').trim()

function normalizeBase(value) {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

export function apiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${apiBase}${normalizedPath}`
}

export function wsUrl() {
  if (typeof window === 'undefined') {
    return configuredWsUrl || 'ws://localhost/ws'
  }
  if (configuredWsUrl) {
    return configuredWsUrl
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

export function shouldUseDemoMode() {
  return typeof window !== 'undefined' && !configuredWsUrl && window.location.hostname.endsWith('github.io')
}
