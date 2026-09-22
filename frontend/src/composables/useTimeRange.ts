// frontend/src/composables/useTimeRange.ts
// 页面级时间范围：快捷范围（今日/本周/近7天/近30天/本月/全部/自定义）→ from/to。
// API 只认 from/to；快捷范围只存在于前端。
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { localTzMinutes, type TotalsParams } from '@/api/analytics'

export type PresetKey = 'today' | 'week' | 'last7' | 'last30' | 'month' | 'all' | 'custom'

export const ACTIVITY_MAX_DAYS = 92 // 与服务端一致
export const ACTIVITY_WINDOW_DAYS = 90

export const PRESETS: { key: PresetKey; label: string }[] = [
  { key: 'today', label: '今日' },
  { key: 'week', label: '本周' },
  { key: 'last7', label: '近 7 天' },
  { key: 'last30', label: '近 30 天' },
  { key: 'month', label: '本月' },
  { key: 'all', label: '全部' },
]

const ALL_START = '2000-01-01'

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

export function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function addDays(base: Date, n: number): Date {
  const d = new Date(base)
  d.setDate(d.getDate() + n)
  return d
}

export function parseDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1)
}

export function daysBetween(from: string, to: string): number {
  return Math.round((parseDate(to).getTime() - parseDate(from).getTime()) / 86400000) + 1
}

export function computePreset(preset: PresetKey, now = new Date()): { from: string; to: string } {
  const today = fmtDate(now)
  switch (preset) {
    case 'today':
      return { from: today, to: today }
    case 'week': {
      const dow = (now.getDay() + 6) % 7 // 周一=0
      return { from: fmtDate(addDays(now, -dow)), to: today }
    }
    case 'last7':
      return { from: fmtDate(addDays(now, -6)), to: today }
    case 'last30':
      return { from: fmtDate(addDays(now, -29)), to: today }
    case 'month':
      return { from: fmtDate(new Date(now.getFullYear(), now.getMonth(), 1)), to: today }
    case 'all':
      return { from: ALL_START, to: today }
    default:
      return { from: today, to: today }
  }
}

export function useTimeRange(defaultPreset: PresetKey = 'last7') {
  const route = useRoute()
  const router = useRouter()

  const initial =
    typeof route.query.from === 'string' && typeof route.query.to === 'string'
      ? { from: route.query.from, to: route.query.to }
      : computePreset(defaultPreset)
  const initialPreset: PresetKey =
    (typeof route.query.preset === 'string' && (route.query.preset as PresetKey)) ||
    (typeof route.query.from === 'string' ? 'custom' : defaultPreset)

  const preset = ref<PresetKey>(initialPreset)
  const from = ref<string>(initial.from)
  const to = ref<string>(initial.to)

  const days = computed(() => Math.max(1, daysBetween(from.value, to.value)))

  /** 全范围参数（daily 类接口：summary / timeseries / apps / sessions） */
  const params = computed<TotalsParams>(() => ({
    from: from.value,
    to: to.value,
    tz: localTzMinutes(),
  }))

  /** 成本受限的活动分析范围（hourly / heatmap / peak）：超过 92 天收敛到最近 90 天 */
  const activityTruncated = computed(() => days.value > ACTIVITY_MAX_DAYS)
  const activityParams = computed<TotalsParams>(() => {
    if (!activityTruncated.value) return params.value
    const now = parseDate(to.value)
    return { from: fmtDate(addDays(now, -(ACTIVITY_WINDOW_DAYS - 1))), to: to.value, tz: localTzMinutes() }
  })

  function syncQuery() {
    void router.replace({
      query: { ...route.query, from: from.value, to: to.value, preset: preset.value },
    })
  }

  function setPreset(next: PresetKey) {
    if (next === 'custom') {
      preset.value = 'custom'
      return
    }
    const range = computePreset(next)
    preset.value = next
    from.value = range.from
    to.value = range.to
    syncQuery()
  }

  function setCustom(nextFrom: string, nextTo: string) {
    if (!nextFrom || !nextTo) return
    preset.value = 'custom'
    from.value = nextFrom <= nextTo ? nextFrom : nextTo
    to.value = nextFrom <= nextTo ? nextTo : nextFrom
    syncQuery()
  }

  return {
    preset,
    from,
    to,
    days,
    params,
    activityParams,
    activityTruncated,
    setPreset,
    setCustom,
  }
}
