const apiBase = normalizeBase(import.meta.env.VITE_API_URL || '/api')
const configuredWsUrl = (import.meta.env.VITE_WS_URL || '').trim()

function normalizeBase(value) {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

export function apiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${apiBase}${normalizedPath}`
}

export function wsUrl() {
  if (configuredWsUrl) {
    return configuredWsUrl
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

export function shouldUseDemoMode() {
  return !configuredWsUrl && window.location.hostname.endsWith('github.io')
}
