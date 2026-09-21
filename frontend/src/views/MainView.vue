<template>
  <div class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Dashboard</p>
        <h1 class="page-title">活动仪表盘</h1>
        <p class="greeting">欢迎回来，{{ username }}</p>
      </div>
      <div class="clock">{{ currentTimeStr }}</div>
    </header>

    <div class="stats-grid">
      <div class="stat-card card" v-for="card in statCards" :key="card.key">
        <div class="stat-icon" :style="{ background: card.iconBg }">
          <i :class="card.icon" :style="{ color: card.iconColor }"></i>
        </div>
        <div class="stat-body">
          <span class="stat-label">{{ card.label }}</span>
          <span class="stat-value">{{ card.value }}</span>
        </div>
        <div class="stat-accent" :style="{ background: card.accentColor }"></div>
      </div>
    </div>

    <div class="dashboard-body">
      <section class="panel apps-panel">
        <div class="panel-header">
          <h2 class="panel-title">应用使用总览</h2>
          <span class="panel-badge">按专注时长排序</span>
        </div>

        <div class="app-list scroll-y">
          <div v-if="topApps.length === 0" class="empty-state">
            <i class="fas fa-inbox"></i>
            <p>暂无应用数据</p>
          </div>
          <div v-for="(app, index) in topApps" :key="app.id" class="app-row">
            <div class="app-rank">{{ String(index + 1).padStart(2, '0') }}</div>
            <div class="app-main">
              <div class="app-top-row">
                <span class="app-name">{{ formatAppName(app.executableName) }}</span>
                <span class="app-last-seen">{{
                  formatRelativeTime(app.summary.lastSeenEndAt)
                }}</span>
              </div>
              <div class="app-bar-row">
                <div class="bar-track">
                  <div
                    class="bar-fill"
                    :style="{
                      width: getFocusRatio(app.summary) + '%',
                      background: getBarColor(index),
                    }"
                  ></div>
                </div>
                <div class="app-durations">
                  <span class="dur-focus">
                    <i class="fas fa-crosshairs"></i>
                    {{ formatDuration(app.summary.totalFocusTimeSeconds) }}
                  </span>
                  <span class="dur-sep">/</span>
                  <span class="dur-total">{{
                    formatDuration(app.summary.totalLifetimeSeconds)
                  }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="panel activity-panel">
        <div class="panel-header">
          <h2 class="panel-title">最近会话</h2>
        </div>
        <ul class="activity-list scroll-y">
          <li v-if="recentActivities.length === 0" class="empty-state">
            <i class="fas fa-inbox"></i>
            <p>暂无记录</p>
          </li>
          <li v-for="activity in recentActivities" :key="activity.id" class="activity-item">
            <div class="activity-dot"></div>
            <div class="activity-content">
              <span class="activity-name">{{ formatAppName(activity.processName) }}</span>
              <span class="activity-meta">
                {{ formatDuration(activity.totalLifetimeSeconds) }} &nbsp;·&nbsp;
                {{ formatTime(activity.sessionStartTime) }} –
                {{ formatTime(activity.sessionEndTime) }}
              </span>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import request from '@/utils/request'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const formatAppName = (name: string): string => name.replace(/\.exe$/i, '')

interface DashboardStats {
  todayFocusSeconds: number
  totalAppsTracked: number
  mostUsedAppToday: string | null
  thisWeekLifetimeSeconds: number
}

interface AppSummary {
  lastSeenEndAt: string
  totalLifetimeSeconds: number
  totalFocusTimeSeconds: number
}

interface WatchedApplication {
  id: number
  executableName: string
  summary: AppSummary
}

interface ProcessSession {
  id: number
  processName: string
  sessionStartTime: string
  sessionEndTime: string
  totalLifetimeSeconds: number
}

const username = ref<string>(authStore.username ?? 'User')

const stats = ref<DashboardStats>({
  todayFocusSeconds: 0,
  totalAppsTracked: 0,
  mostUsedAppToday: null,
  thisWeekLifetimeSeconds: 0,
})

const topApps = ref<WatchedApplication[]>([])
const recentActivities = ref<ProcessSession[]>([])

const now = ref(new Date())
let clockTimer: ReturnType<typeof setInterval> | null = null
let dataTimer: ReturnType<typeof setInterval> | null = null

const currentTimeStr = computed(() => {
  return now.value.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
})

const formatDuration = (totalSeconds: number): string => {
  if (!totalSeconds || totalSeconds < 60) return `${Math.round(totalSeconds || 0)}秒`
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  if (days > 0) return `${days}天${hours > 0 ? ' ' + hours + '时' : ''}`
  if (hours > 0) return `${hours}时${minutes > 0 ? ' ' + minutes + '分' : ''}`
  return `${minutes}分钟`
}

const formatTime = (iso: string): string => {
  return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const formatRelativeTime = (iso: string): string => {
  const diff = (now.value.getTime() - new Date(iso).getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}

const getFocusRatio = (summary: AppSummary): number => {
  if (!summary.totalLifetimeSeconds) return 0
  return Math.min(
    100,
    Math.round((summary.totalFocusTimeSeconds / summary.totalLifetimeSeconds) * 100),
  )
}

const BAR_COLORS = ['#4f9cf9', '#34c88a', '#f5a623', '#e85d75', '#a78bfa', '#38bdf8']
const getBarColor = (index: number): string => BAR_COLORS[index % BAR_COLORS.length]!

const statCards = computed(() => [
  {
    key: 'focus',
    label: '今日专注时长',
    value: formatDuration(stats.value.todayFocusSeconds),
    icon: 'fas fa-crosshairs',
    iconBg: 'rgba(79,156,249,0.12)',
    iconColor: '#4f9cf9',
    accentColor: '#4f9cf9',
  },
  {
    key: 'apps',
    label: '追踪应用数',
    value: `${stats.value.totalAppsTracked} 个`,
    icon: 'fas fa-th-large',
    iconBg: 'rgba(52,200,138,0.12)',
    iconColor: '#34c88a',
    accentColor: '#34c88a',
  },
  {
    key: 'top',
    label: '今日最常用',
    value: stats.value.mostUsedAppToday ? formatAppName(stats.value.mostUsedAppToday) : '—',
    icon: 'fas fa-crown',
    iconBg: 'rgba(245,166,35,0.12)',
    iconColor: '#f5a623',
    accentColor: '#f5a623',
  },
  {
    key: 'week',
    label: '本周运行时长',
    value: formatDuration(stats.value.thisWeekLifetimeSeconds),
    icon: 'fas fa-calendar-week',
    iconBg: 'rgba(167,139,250,0.12)',
    iconColor: '#a78bfa',
    accentColor: '#a78bfa',
  },
])

const fetchData = async () => {
  if (!authStore.isAuthenticated) {
    router.push('/login')
    return
  }
  try {
    const [statsRes, appsRes, activityRes] = await Promise.all([
      request.get('/dashboard/stats'),
      request.get('/dashboard/apps?sort_by=focus_time'),
      request.get('/dashboard/recent-activity?limit=10'),
    ])
    stats.value = statsRes as unknown as DashboardStats
    topApps.value = appsRes as unknown as WatchedApplication[]
    recentActivities.value = activityRes as unknown as ProcessSession[]
  } catch (error) {
    console.error('无法加载仪表盘数据:', error)
  }
}

onMounted(() => {
  fetchData()
  clockTimer = setInterval(() => {
    now.value = new Date()
  }, 1000)
  dataTimer = setInterval(fetchData, 60000)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
  if (dataTimer) clearInterval(dataTimer)
})
</script>

<style scoped>
.greeting {
  margin: var(--sp-1) 0 0;
  font-size: 0.9rem;
  color: var(--text-muted);
}
.clock {
  font-family: var(--font-mono);
  font-size: 1.05rem;
  color: var(--text-faint);
  padding-bottom: 0.25rem;
  white-space: nowrap;
}

/* ── 统计卡 ── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-4);
  margin-bottom: var(--sp-5);
}
.stat-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: 1.1rem 1.1rem 1.1rem 0.9rem;
  overflow: hidden;
  transition:
    border-color 0.2s,
    transform 0.2s;
}
.stat-card:hover {
  border-color: var(--border-strong);
  transform: translateY(-2px);
}
.stat-accent {
  position: absolute;
  left: 0;
  top: 20%;
  bottom: 20%;
  width: 3px;
  border-radius: 0 2px 2px 0;
  opacity: 0.85;
}
.stat-icon {
  width: 42px;
  height: 42px;
  border-radius: var(--r-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 1rem;
}
.stat-body {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}
.stat-label {
  font-size: 0.75rem;
  color: var(--text-faint);
  white-space: nowrap;
}
.stat-value {
  font-size: 1.3rem;
  font-weight: 600;
  color: var(--text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── 主体两栏 ── */
.dashboard-body {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 1.2fr);
  gap: var(--sp-4);
  align-items: start;
}

/* ── 应用总览 ── */
.app-list {
  padding: 0.4rem 0;
  max-height: 480px;
}
.app-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: 0.8rem 1.4rem;
  transition: background 0.15s;
}
.app-row:hover {
  background: var(--surface-hover);
}
.app-rank {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-faint);
  width: 20px;
  flex-shrink: 0;
}
.app-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.app-top-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--sp-2);
}
.app-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-last-seen {
  font-size: 0.72rem;
  color: var(--text-faint);
  flex-shrink: 0;
}
.app-bar-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.bar-track {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s ease;
}
.app-durations {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.72rem;
  flex-shrink: 0;
}
.dur-focus {
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.3rem;
}
.dur-focus i {
  font-size: 0.6rem;
  opacity: 0.6;
}
.dur-sep {
  color: var(--text-faint);
}
.dur-total {
  color: var(--text-faint);
}

/* ── 最近会话 ── */
.activity-list {
  list-style: none;
  margin: 0;
  padding: 0.4rem 0;
  max-height: 480px;
}
.activity-item {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: 0.7rem 1.4rem;
  transition: background 0.15s;
}
.activity-item:hover {
  background: var(--surface-hover);
}
.activity-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(79, 156, 249, 0.25);
  border: 1.5px solid var(--accent);
  margin-top: 5px;
  flex-shrink: 0;
}
.activity-content {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}
.activity-name {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.activity-meta {
  font-size: 0.72rem;
  color: var(--text-faint);
  font-family: var(--font-mono);
}

@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .dashboard-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 640px) {
  .stats-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--sp-2);
  }
}
</style>
