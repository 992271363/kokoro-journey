<template>
  <div class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Dashboard</p>
        <h1 class="page-title">概览</h1>
        <p class="sub">欢迎回来，{{ username }} · {{ rangeLabel }}</p>
      </div>
      <TimeRangePicker
        :preset="preset"
        :from="from"
        :to="to"
        @preset="setPreset"
        @custom="setCustom"
      />
    </header>

    <p v-if="error" class="flash err"><i class="fas fa-triangle-exclamation"></i> {{ error }}</p>

    <!-- 总体卡片 -->
    <div class="stats-grid">
      <div v-for="card in cards" :key="card.key" class="stat-card card">
        <div class="stat-body">
          <span class="stat-label">{{ card.label }}</span>
          <span class="stat-value">{{ card.value }}</span>
        </div>
        <span class="stat-delta" :class="deltaClass(card.delta)">
          <template v-if="card.delta === null">—</template>
          <template v-else>
            <i class="fas" :class="card.delta >= 0 ? 'fa-arrow-up' : 'fa-arrow-down'"></i>
            {{ Math.abs(card.delta).toFixed(1) }}%
          </template>
        </span>
        <div class="stat-accent" :style="{ background: card.color }"></div>
      </div>
    </div>

    <!-- 趋势 -->
    <section class="panel">
      <div class="panel-header">
        <h2 class="panel-title">专注 / 运行趋势</h2>
        <span class="panel-badge">{{ rangeLabel }}</span>
      </div>
      <div class="chart-box">
        <div v-if="loadingTrend" class="hint pad">加载中…</div>
        <ActivityTrendChart v-else :points="trend" />
      </div>
    </section>

    <div class="lower-grid">
      <!-- 应用排行 -->
      <section class="panel apps-panel">
        <div class="panel-header">
          <h2 class="panel-title">应用排行</h2>
          <input
            v-model="appQuery"
            class="input search"
            type="search"
            placeholder="搜索应用…"
          />
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th class="sortable" @click="sortBy('name')">
                  应用 <i v-if="sort === 'name'" class="fas" :class="sortIcon"></i>
                </th>
                <th class="num sortable" @click="sortBy('focus')">
                  专注 <i v-if="sort === 'focus'" class="fas" :class="sortIcon"></i>
                </th>
                <th class="num sortable" @click="sortBy('lifetime')">
                  运行 <i v-if="sort === 'lifetime'" class="fas" :class="sortIcon"></i>
                </th>
                <th class="num">占比</th>
                <th class="num sortable" @click="sortBy('active_days')">
                  活跃 <i v-if="sort === 'active_days'" class="fas" :class="sortIcon"></i>
                </th>
                <th class="num">平均单次</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loadingApps">
                <td colspan="6" class="hint pad">加载中…</td>
              </tr>
              <tr v-else-if="apps.length === 0">
                <td colspan="6" class="hint pad">该范围暂无数据</td>
              </tr>
              <tr
                v-for="app in apps"
                v-else
                :key="app.appId"
                class="clickable"
                @click="openApp(app.appId)"
              >
                <td class="cell-name" :title="app.executableName">{{ appName(app.executableName) }}</td>
                <td class="num">{{ formatDuration(app.focusSeconds) }}</td>
                <td class="num">{{ formatDuration(app.lifetimeSeconds) }}</td>
                <td class="num">{{ formatPercent(app.focusRatio) }}</td>
                <td class="num">{{ app.activeDays }} 天</td>
                <td class="num">{{ formatDuration(app.avgSessionFocusSeconds) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="pager">
          <span class="pager-info">共 {{ appsTotal }} 个应用</span>
          <button class="btn btn-icon" :disabled="appsPage <= 1" @click="goPage(appsPage - 1)">
            <i class="fas fa-chevron-left"></i>
          </button>
          <span class="pager-page">{{ appsPage }} / {{ appsPageCount }}</span>
          <button
            class="btn btn-icon"
            :disabled="appsPage >= appsPageCount"
            @click="goPage(appsPage + 1)"
          >
            <i class="fas fa-chevron-right"></i>
          </button>
        </div>
      </section>

      <!-- 最近活动 -->
      <section class="panel recent-panel">
        <div class="panel-header">
          <h2 class="panel-title">最近活动</h2>
          <span class="panel-badge">{{ sessions.length }} 条</span>
        </div>
        <ul class="session-list scroll-y">
          <li v-if="loadingSessions" class="hint pad">加载中…</li>
          <li v-else-if="sessions.length === 0" class="hint pad">该范围暂无会话</li>
          <li v-for="s in sessions" v-else :key="s.id" class="session-item">
            <div class="session-row" @click="toggleSession(s.id)">
              <div class="session-main">
                <span class="session-name">{{ appName(s.executableName) }}</span>
                <span class="session-meta">
                  {{ formatDateTime(s.start) }}
                  <template v-if="s.end"> – {{ formatTime(s.end) }}</template>
                </span>
              </div>
              <div class="session-durations">
                <span class="dur">运行 {{ formatDurationCompact(s.lifetimeSeconds) }}</span>
                <span class="dur focus">专注 {{ formatDurationCompact(s.focusSeconds) }}</span>
                <i
                  class="fas fa-chevron-down toggle"
                  :class="{ open: expandedId === s.id }"
                ></i>
              </div>
            </div>
            <div v-if="expandedId === s.id" class="activity-list">
              <div v-if="activitiesLoading" class="hint">加载中…</div>
              <div v-else-if="activities.length === 0" class="hint">无窗口活动记录</div>
              <ul v-else>
                <li v-for="(a, i) in activities" :key="i" class="activity-item">
                  <span class="activity-time">{{ formatTime(a.start) }}</span>
                  <span class="activity-title" :title="a.windowTitle || '(无标题)'">
                    {{ a.windowTitle || '(无标题)' }}
                  </span>
                  <span class="activity-dur">{{ formatDurationCompact(a.durationSeconds) }}</span>
                </li>
              </ul>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <AppDetailDrawer
      :app-id="drawerAppId"
      :from="activityParams.from"
      :to="activityParams.to"
      :tz="tz"
      :truncated="activityTruncated"
      @close="drawerAppId = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useTimeRange } from '@/composables/useTimeRange'
import {
  getApps,
  getSessionActivities,
  getSessions,
  getSummary,
  getTimeseries,
  localTzMinutes,
  type ActivityItem,
  type AnalyticsSummary,
  type AppRankItem,
  type SessionItem,
  type TimeseriesPoint,
} from '@/api/analytics'
import {
  appName,
  formatDateTime,
  formatDuration,
  formatDurationCompact,
  formatPercent,
  formatTime,
} from '@/utils/format'
import TimeRangePicker from '@/components/TimeRangePicker.vue'
import ActivityTrendChart from '@/components/charts/ActivityTrendChart.vue'
import AppDetailDrawer from '@/components/AppDetailDrawer.vue'

const authStore = useAuthStore()
const username = authStore.username ?? 'User'
const tz = localTzMinutes()

const { preset, from, to, params, activityParams, activityTruncated, setPreset, setCustom } =
  useTimeRange('last7')

const summary = ref<AnalyticsSummary | null>(null)
const trend = ref<TimeseriesPoint[]>([])
const apps = ref<AppRankItem[]>([])
const appsTotal = ref(0)
const sessions = ref<SessionItem[]>([])

const loadingTrend = ref(false)
const loadingApps = ref(false)
const loadingSessions = ref(false)
const error = ref('')

const appQuery = ref('')
const sort = ref<'focus' | 'lifetime' | 'active_days' | 'name'>('focus')
const order = ref<'asc' | 'desc'>('desc')
const appsPage = ref(1)
const pageSize = 8
const appsPageCount = computed(() => Math.max(1, Math.ceil(appsTotal.value / pageSize)))

const expandedId = ref<number | null>(null)
const activities = ref<ActivityItem[]>([])
const activitiesLoading = ref(false)
const drawerAppId = ref<number | null>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null

const rangeLabel = computed(() => `${from.value} ~ ${to.value}`)

const deltaClass = (v: number | null) =>
  v === null ? 'flat' : v >= 0 ? 'up' : 'down'

const cards = computed(() => {
  const cur = summary.value?.current
  const chg = summary.value?.change
  return [
    {
      key: 'focus',
      label: '专注时长',
      value: formatDuration(cur?.focusSeconds),
      delta: chg?.focus ?? null,
      color: '#4f9cf9',
    },
    {
      key: 'lifetime',
      label: '运行时长',
      value: formatDuration(cur?.lifetimeSeconds),
      delta: chg?.lifetime ?? null,
      color: '#34c88a',
    },
    {
      key: 'apps',
      label: '活跃应用',
      value: `${cur?.activeApps ?? 0} 个`,
      delta: chg?.activeApps ?? null,
      color: '#f5a623',
    },
    {
      key: 'days',
      label: '活跃天数',
      value: `${cur?.activeDays ?? 0} 天`,
      delta: chg?.activeDays ?? null,
      color: '#a78bfa',
    },
  ]
})

const sortIcon = computed(() => (order.value === 'desc' ? 'fa-arrow-down' : 'fa-arrow-up'))

function reportError(e: unknown, fallback: string) {
  const err = e as { response?: { data?: { detail?: string } }; message?: string }
  error.value = err?.response?.data?.detail || err?.message || fallback
}

async function loadSummary() {
  error.value = ''
  loadingTrend.value = true
  try {
    const [s, t] = await Promise.all([getSummary(params.value), getTimeseries(params.value)])
    summary.value = s
    trend.value = t.points
  } catch (e) {
    reportError(e, '无法加载概览数据')
  } finally {
    loadingTrend.value = false
  }
}

async function loadApps() {
  loadingApps.value = true
  try {
    const res = await getApps({
      ...params.value,
      q: appQuery.value,
      sort: sort.value,
      order: order.value,
      page: appsPage.value,
      pageSize,
    })
    apps.value = res.items
    appsTotal.value = res.total
  } catch (e) {
    reportError(e, '无法加载应用排行')
  } finally {
    loadingApps.value = false
  }
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    const res = await getSessions({ ...params.value, page: 1, pageSize: 10 })
    sessions.value = res.items
    expandedId.value = null
  } catch (e) {
    reportError(e, '无法加载最近活动')
  } finally {
    loadingSessions.value = false
  }
}

function sortBy(key: typeof sort.value) {
  if (sort.value === key) {
    order.value = order.value === 'desc' ? 'asc' : 'desc'
  } else {
    sort.value = key
    order.value = key === 'name' ? 'asc' : 'desc'
  }
  appsPage.value = 1
  void loadApps()
}

function goPage(page: number) {
  appsPage.value = page
  void loadApps()
}

function openApp(appId: number) {
  drawerAppId.value = appId
}

async function toggleSession(id: number) {
  if (expandedId.value === id) {
    expandedId.value = null
    return
  }
  expandedId.value = id
  activities.value = []
  activitiesLoading.value = true
  try {
    activities.value = await getSessionActivities(id)
  } catch (e) {
    reportError(e, '无法加载窗口活动')
  } finally {
    activitiesLoading.value = false
  }
}

watch(
  () => [from.value, to.value],
  () => {
    appsPage.value = 1
    void loadSummary()
    void loadApps()
    void loadSessions()
  },
)

watch(appQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    appsPage.value = 1
    void loadApps()
  }, 300)
})

onMounted(() => {
  void loadSummary()
  void loadApps()
  void loadSessions()
})
</script>

<style scoped>
.sub {
  margin: var(--sp-1) 0 0;
  font-size: 0.88rem;
  color: var(--text-muted);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
}
.stat-card {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 1.05rem 1.1rem 1.05rem 1rem;
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
.stat-delta {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  flex-shrink: 0;
}
.stat-delta.up {
  color: var(--ok);
}
.stat-delta.down {
  color: var(--danger);
}
.stat-delta.flat {
  color: var(--text-faint);
}

.chart-box {
  height: 280px;
  padding: var(--sp-3);
}
.pad {
  padding: var(--sp-5);
}

.lower-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr);
  gap: var(--sp-4);
  margin-top: var(--sp-4);
  align-items: start;
}

.search {
  width: 180px;
  padding: 0.4rem 0.6rem;
  font-size: 0.8rem;
}
.table-wrap {
  overflow-x: auto;
}
.sortable {
  cursor: pointer;
  user-select: none;
}
.sortable i {
  margin-left: 0.25rem;
  font-size: 0.65rem;
  color: var(--accent);
}
.num {
  text-align: right;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: var(--text-muted);
}
.cell-name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}
.clickable {
  cursor: pointer;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  border-top: 1px solid var(--border);
}
.pager-info {
  margin-right: auto;
  font-size: 0.75rem;
  color: var(--text-faint);
}
.pager-page {
  font-size: 0.78rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.session-list {
  list-style: none;
  margin: 0;
  padding: 0.3rem 0;
  max-height: 520px;
}
.session-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 0.7rem 1.2rem;
  cursor: pointer;
  transition: background 0.15s;
}
.session-row:hover {
  background: var(--surface-hover);
}
.session-main {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
}
.session-name {
  font-size: 0.86rem;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-meta {
  font-size: 0.7rem;
  color: var(--text-faint);
}
.session-durations {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}
.dur {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
}
.dur.focus {
  color: #93c5fd;
}
.toggle {
  font-size: 0.65rem;
  color: var(--text-faint);
  transition: transform 0.2s;
}
.toggle.open {
  transform: rotate(180deg);
}

.activity-list {
  padding: 0.2rem 1.2rem 0.7rem 2rem;
}
.activity-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.activity-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: 0.35rem 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 0.76rem;
}
.activity-time {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--text-faint);
  flex-shrink: 0;
}
.activity-title {
  flex: 1;
  min-width: 0;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.activity-dur {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--text-faint);
  flex-shrink: 0;
}

@media (max-width: 1100px) {
  .lower-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 560px) {
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
