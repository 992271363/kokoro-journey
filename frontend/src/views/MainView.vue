<template>
  <div class="dashboard">
    <div class="dashboard-header">
      <div class="header-text">
        <p class="greeting">欢迎回来，{{ username }}</p>
        <h1>活动仪表盘</h1>
      </div>
      <div class="header-time">{{ currentTimeStr }}</div>
    </div>

    <div class="stats-grid">
      <div class="stat-card" v-for="card in statCards" :key="card.key">
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
          <h2>应用使用总览</h2>
          <span class="panel-badge">按专注时长排序</span>
        </div>

        <div class="app-list">
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
          <h2>最近会话</h2>
        </div>
        <ul class="activity-list">
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
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap');

.dashboard {
  font-family: 'DM Sans', sans-serif;
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem 2.5rem 3rem;
  color: #e2e8f0;
}

/* ── Header ── */
.dashboard-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 2.5rem;
}
.greeting {
  margin: 0 0 0.25rem;
  font-size: 0.9rem;
  color: #64748b;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.dashboard-header h1 {
  margin: 0;
  font-size: 2rem;
  font-weight: 600;
  color: #f1f5f9;
  letter-spacing: -0.02em;
}
.header-time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.1rem;
  color: #475569;
  padding-bottom: 0.25rem;
}

/* ── Stat Cards ── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 2rem;
}
.stat-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 1rem;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 14px;
  padding: 1.25rem 1.25rem 1.25rem 1rem;
  overflow: hidden;
  transition:
    border-color 0.2s,
    transform 0.2s;
}
.stat-card:hover {
  border-color: rgba(255, 255, 255, 0.14);
  transform: translateY(-2px);
}
.stat-accent {
  position: absolute;
  left: 0;
  top: 20%;
  bottom: 20%;
  width: 3px;
  border-radius: 0 2px 2px 0;
  opacity: 0.8;
}
.stat-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
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
  color: #64748b;
  white-space: nowrap;
  letter-spacing: 0.02em;
}
.stat-value {
  font-size: 1.35rem;
  font-weight: 600;
  color: #f1f5f9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Body Layout ── */
.dashboard-body {
  display: grid;
  grid-template-columns: 3fr 1.2fr;
  gap: 1.25rem;
  align-items: flex-start;
}

/* ── Panels ── */
.panel {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 16px;
  overflow: hidden;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem 1rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.panel-header h2 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: #cbd5e1;
  letter-spacing: 0.01em;
}
.panel-badge {
  font-size: 0.7rem;
  color: #475569;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  padding: 0.2rem 0.65rem;
}

/* ── App List ── */
.app-list {
  padding: 0.5rem 0;
  max-height: 480px;
  overflow-y: auto;
}
.app-list::-webkit-scrollbar {
  width: 4px;
}
.app-list::-webkit-scrollbar-track {
  background: transparent;
}
.app-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}

.app-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.85rem 1.5rem;
  transition: background 0.15s;
}
.app-row:hover {
  background: rgba(255, 255, 255, 0.03);
}
.app-rank {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #334155;
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
  gap: 0.5rem;
}
.app-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-last-seen {
  font-size: 0.72rem;
  color: #475569;
  flex-shrink: 0;
}
.app-bar-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.bar-track {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.07);
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
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 0.3rem;
}
.dur-focus i {
  font-size: 0.6rem;
  opacity: 0.6;
}
.dur-sep {
  color: #334155;
}
.dur-total {
  color: #475569;
}

/* ── Activity Panel ── */
.activity-list {
  list-style: none;
  margin: 0;
  padding: 0.5rem 0;
  max-height: 480px;
  overflow-y: auto;
}
.activity-list::-webkit-scrollbar {
  width: 4px;
}
.activity-list::-webkit-scrollbar-track {
  background: transparent;
}
.activity-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}

.activity-item {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 1.5rem;
  transition: background 0.15s;
}
.activity-item:hover {
  background: rgba(255, 255, 255, 0.03);
}
.activity-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #1e3a5f;
  border: 1.5px solid #3b82f6;
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
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.activity-meta {
  font-size: 0.72rem;
  color: #475569;
  font-family: 'JetBrains Mono', monospace;
}

/* ── Empty State ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 3rem 1rem;
  color: #334155;
  font-size: 0.85rem;
}
.empty-state i {
  font-size: 1.5rem;
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .dashboard-body {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .dashboard {
    padding: 1rem;
  }
  .stats-grid {
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }
  .dashboard-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }
}
</style>
