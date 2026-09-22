import { describe, it, expect } from 'vitest'
import {
  ACTIVITY_MAX_DAYS,
  PRESETS,
  computePreset,
  daysBetween,
  fmtDate,
  parseDate,
} from '@/composables/useTimeRange'

const NOW = new Date(2026, 8, 22) // 2026-09-22（周二）

describe('useTimeRange 纯函数', () => {
  it('快捷范围 → from/to', () => {
    expect(computePreset('today', NOW)).toEqual({ from: '2026-09-22', to: '2026-09-22' })
    expect(computePreset('week', NOW)).toEqual({ from: '2026-09-21', to: '2026-09-22' })
    expect(computePreset('last7', NOW)).toEqual({ from: '2026-09-16', to: '2026-09-22' })
    expect(computePreset('last30', NOW)).toEqual({ from: '2026-08-24', to: '2026-09-22' })
    expect(computePreset('month', NOW)).toEqual({ from: '2026-09-01', to: '2026-09-22' })
    expect(computePreset('all', NOW)).toEqual({ from: '2000-01-01', to: '2026-09-22' })
  })

  it('本周从周一开始', () => {
    // 2026-09-20 是周日 → 本周应为 09-14(周一) ~ 09-20
    const sunday = new Date(2026, 8, 20)
    expect(computePreset('week', sunday)).toEqual({ from: '2026-09-14', to: '2026-09-20' })
  })

  it('日期工具', () => {
    expect(fmtDate(NOW)).toBe('2026-09-22')
    expect(daysBetween('2026-09-16', '2026-09-22')).toBe(7)
    expect(daysBetween('2026-09-22', '2026-09-22')).toBe(1)
    expect(parseDate('2026-09-22').getFullYear()).toBe(2026)
  })

  it('预设集合与活动分析上限', () => {
    expect(PRESETS.map((p) => p.key)).toEqual([
      'today',
      'week',
      'last7',
      'last30',
      'month',
      'all',
    ])
    expect(ACTIVITY_MAX_DAYS).toBe(92)
  })
})
