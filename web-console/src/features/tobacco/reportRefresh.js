// Schedule after completion so a slow request cannot overlap the next refresh.
export function createReportRefresher({
  load,
  isVisible,
  intervalMs = 15000,
  schedule = setTimeout,
  cancel = clearTimeout,
}) {
  let active = false
  let running = false
  let timer = null

  async function refresh(background = true) {
    if (!active || running) return
    cancel(timer)
    timer = null
    running = true
    try {
      if (isVisible()) await load({ background })
    } finally {
      running = false
      if (active) timer = schedule(() => refresh(), intervalMs)
    }
  }

  return {
    start() {
      if (active) return
      active = true
      return refresh(false)
    },
    refresh,
    stop() {
      active = false
      cancel(timer)
      timer = null
    },
  }
}
