import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

import request from '@/utils/request'
import {
  getAppDetail,
  getApps,
  getHeatmap,
  getHourly,
  getSessionActivities,
  getSessions,
  getSummary,
  getTimeseries,
  localTzMinutes,
} from '@/api/analytics'

beforeEach(() => {
  vi.clearAllMocks()
  ;(request.get as ReturnType<typeof vi.fn>).mockResolvedValue({})
})

describe('analytics api', () => {
  it('summary / timeseries 传 from,to', async () => {
    await getSummary({ from: '2026-09-15', to: '2026-09-21' })
    await getTimeseries({ from: '2026-09-15', to: '2026-09-21' })
    expect(request.get).toHaveBeenNthCalledWith(1, '/analytics/summary', {
      params: { from: '2026-09-15', to: '2026-09-21' },
    })
    expect(request.get).toHaveBeenNthCalledWith(2, '/analytics/timeseries', {
      params: { from: '2026-09-15', to: '2026-09-21' },
    })
  })

  it('apps 参数（含 pageSize / include）', async () => {
    await getApps({
      from: '2026-09-15',
      to: '2026-09-21',
      tz: 480,
      q: 'code',
      sort: 'focus',
      order: 'desc',
      page: 2,
      pageSize: 20,
      include: 'peak',
    })
    expect(request.get).toHaveBeenCalledWith('/analytics/apps', {
      params: {
        from: '2026-09-15',
        to: '2026-09-21',
        tz: 480,
        q: 'code',
        sort: 'focus',
        order: 'desc',
        page: 2,
        pageSize: 20,
        include: 'peak',
      },
    })
  })

  it('app detail / sessions / activities 路径', async () => {
    await getAppDetail(7, { from: '2026-09-15', to: '2026-09-21', tz: 480 })
    await getSessions({ from: '2026-09-15', to: '2026-09-21', page: 1, pageSize: 10 })
    await getSessionActivities(42)
    expect(request.get).toHaveBeenNthCalledWith(1, '/analytics/apps/7', {
      params: { from: '2026-09-15', to: '2026-09-21', tz: 480 },
    })
    expect(request.get).toHaveBeenNthCalledWith(2, '/analytics/sessions', {
      params: { from: '2026-09-15', to: '2026-09-21', page: 1, pageSize: 10 },
    })
    expect(request.get).toHaveBeenNthCalledWith(3, '/analytics/sessions/42/activities')
  })

  it('activity hourly / heatmap 路径', async () => {
    await getHourly({ from: '2026-09-15', to: '2026-09-21', tz: 480, metric: 'opens' })
    await getHeatmap({ from: '2026-09-15', to: '2026-09-21', tz: 480 })
    expect(request.get).toHaveBeenNthCalledWith(1, '/analytics/activity/hourly', {
      params: { from: '2026-09-15', to: '2026-09-21', tz: 480, metric: 'opens' },
    })
    expect(request.get).toHaveBeenNthCalledWith(2, '/analytics/activity/heatmap', {
      params: { from: '2026-09-15', to: '2026-09-21', tz: 480 },
    })
  })

  it('localTzMinutes 返回分钟偏移（数字）', () => {
    expect(typeof localTzMinutes()).toBe('number')
  })
})
