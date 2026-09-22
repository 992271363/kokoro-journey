// frontend/src/api/analytics.ts
// 活动分析查询层（服务端聚合）
import request from '@/utils/request'

/** tz = 分钟偏移，本地时间 = UTC + tz（如 UTC+8 → 480） */
export function localTzMinutes(): number {
  return -new Date().getTimezoneOffset()
}

export interface RangeParams {
  from: string
  to: string
}

export interface TotalsParams extends RangeParams {
  tz?: number
}

export interface AnalyticsRangeInfo {
  from: string
  to: string
  days: number
}

export interface AnalyticsMetrics {
  focusSeconds: number
  lifetimeSeconds: number
  activeApps: number
  activeDays: number
  focusRatio: number
}

export interface AnalyticsChange {
  focus: number | null
  lifetime: number | null
  activeApps: number | null
  activeDays: number | null
}

export interface MostUsedApp {
  appId: number
  executableName: string
  focusSeconds: number
}

export interface AnalyticsSummary {
  range: AnalyticsRangeInfo
  current: AnalyticsMetrics
  previous: AnalyticsMetrics
  change: AnalyticsChange
  mostUsedApp: MostUsedApp | null
}

export interface TimeseriesPoint {
  date: string
  focusSeconds: number
  lifetimeSeconds: number
}

export interface AppRankItem {
  appId: number
  executableName: string
  focusSeconds: number
  lifetimeSeconds: number
  focusRatio: number
  activeDays: number
  sessionCount: number
  avgSessionFocusSeconds: number
  peakHour: number | null
  firstSeenAt: string | null
  lastSeenAt: string | null
}

export interface Paged<T> {
  total: number
  page: number
  pageSize: number
  items: T[]
}

export interface SessionItem {
  id: number
  appId: number
  executableName: string
  processName: string
  start: string
  end: string | null
  lifetimeSeconds: number
  focusSeconds: number
  activityCount: number
}

export interface ActivityItem {
  windowTitle: string | null
  start: string | null
  end: string | null
  durationSeconds: number
}

export interface AppDetail {
  appId: number
  executableName: string
  executablePath: string
  summary: {
    focusSeconds: number
    lifetimeSeconds: number
    focusRatio: number
    activeDays: number
    sessionCount: number
    avgSessionFocusSeconds: number
    firstSeenAt: string | null
    lastSeenAt: string | null
  }
  series: TimeseriesPoint[]
  hourly: number[]
  topWindows: { windowTitle: string | null; focusSeconds: number }[]
  recentSessions: {
    id: number
    processName: string
    start: string
    end: string | null
    lifetimeSeconds: number
    focusSeconds: number
  }[]
}

export interface AppsQuery extends TotalsParams {
  q?: string
  sort?: 'focus' | 'lifetime' | 'active_days' | 'name'
  order?: 'asc' | 'desc'
  page?: number
  pageSize?: number
  include?: '' | 'peak'
}

export interface SessionsQuery extends TotalsParams {
  appId?: number
  page?: number
  pageSize?: number
  order?: 'start_desc'
}

export function getSummary(params: RangeParams) {
  return request.get('/analytics/summary', { params }) as unknown as Promise<AnalyticsSummary>
}

export function getTimeseries(params: RangeParams & { bucket?: 'day' }) {
  return request.get('/analytics/timeseries', { params }) as unknown as Promise<{
    bucket: 'day'
    points: TimeseriesPoint[]
  }>
}

export function getApps(params: AppsQuery) {
  return request.get('/analytics/apps', { params }) as unknown as Promise<Paged<AppRankItem>>
}

export function getAppDetail(appId: number, params: TotalsParams) {
  return request.get(`/analytics/apps/${appId}`, { params }) as unknown as Promise<AppDetail>
}

export function getSessions(params: SessionsQuery) {
  return request.get('/analytics/sessions', { params }) as unknown as Promise<Paged<SessionItem>>
}

export function getSessionActivities(sessionId: number) {
  return request.get(
    `/analytics/sessions/${sessionId}/activities`,
  ) as unknown as Promise<ActivityItem[]>
}

export function getHourly(params: TotalsParams & { metric?: 'focus' | 'opens' | 'closes' }) {
  return request.get('/analytics/activity/hourly', { params }) as unknown as Promise<number[]>
}

export function getHeatmap(params: TotalsParams) {
  return request.get('/analytics/activity/heatmap', { params }) as unknown as Promise<number[][]>
}
