// frontend/src/utils/format.ts

export function formatDuration(totalSeconds?: number | null): string {
  const s = Math.max(0, Math.round(Number(totalSeconds ?? 0)))
  if (s < 60) return `${s} 秒`
  const days = Math.floor(s / 86400)
  const hours = Math.floor((s % 86400) / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  if (days > 0) return `${days} 天 ${hours} 时`
  if (hours > 0) return `${hours} 时 ${minutes} 分`
  return `${minutes} 分`
}

/** 紧凑时长：2h31m / 12m / 45s（用于图表与列表） */
export function formatDurationCompact(totalSeconds?: number | null): string {
  const s = Math.max(0, Math.round(Number(totalSeconds ?? 0)))
  if (s < 60) return `${s}s`
  const hours = Math.floor(s / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  if (hours > 0) return minutes > 0 ? `${hours}h${minutes}m` : `${hours}h`
  return `${minutes}m`
}

export function formatSize(bytes?: number | null): string {
  const n = Number(bytes ?? 0)
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB']
  let value = n / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[i]}`
}

export function formatDateTime(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatTime(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

export function formatPercent(ratio?: number | null): string {
  return `${Math.round(Number(ratio ?? 0) * 100)}%`
}

export function shortDate(iso: string): string {
  return iso.slice(5) // MM-DD
}

/** 去掉 .exe 后缀 */
export function appName(name?: string | null): string {
  return (name ?? '').replace(/\.exe$/i, '')
}
