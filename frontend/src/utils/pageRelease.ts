/** Static HTML is already public; this check sends no device token or schedule data. */
export function watchPageRelease(canReload: () => boolean): () => void {
  const current = document.querySelector<HTMLMetaElement>('meta[name="roombeacon-release"]')?.content
  if (!current) return () => {}
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout>
  let stopped = false
  async function check() {
    controller = new AbortController()
    const timeout = setTimeout(() => controller?.abort(), 15000)
    try {
      if (!canReload() || document.hidden) return
      const entry = new URL(location.pathname, location.origin)
      const response = await fetch(entry, { cache: 'no-store', signal: controller.signal, redirect: 'error' })
      if (!response.ok || !response.headers.get('content-type')?.includes('text/html')) return
      const html = new DOMParser().parseFromString(await response.text(), 'text/html')
      const next = html.querySelector<HTMLMetaElement>('meta[name="roombeacon-release"]')?.content
      if (!next || next === current || !/^[A-Za-z0-9._-]{1,100}$/.test(next)) return
      const last = Number(sessionStorage.getItem('roombeacon_last_reload') || 0)
      if (Date.now() - last < 600000) return
      const assets = Array.from(html.querySelectorAll<HTMLScriptElement>('script[type="module"][src]'))
      if (!assets.length) return
      for (const script of assets) {
        const url = new URL(script.getAttribute('src')!, entry)
        if (url.origin !== location.origin) return
        const asset = await fetch(url, { method: 'HEAD', cache: 'no-store', signal: controller.signal, redirect: 'error' })
        if (!asset.ok || !/javascript/.test(asset.headers.get('content-type') || '')) return
      }
      if (stopped || !canReload()) return
      sessionStorage.setItem('roombeacon_last_reload', String(Date.now()))
      location.reload()
    } catch {
      if (!controller.signal.aborted) console.warn('Page release check unavailable')
    } finally {
      clearTimeout(timeout)
      if (!stopped) timer = setTimeout(check, 300000)
    }
  }
  timer = setTimeout(check, 300000)
  return () => { stopped = true; clearTimeout(timer); controller?.abort() }
}
