<template>
  <div v-if="appId !== null" class="drawer-mask" @click.self="emit('close')">
    <aside class="drawer">
      <header class="drawer-header">
        <div>
          <p class="eyebrow">应用详情</p>
          <h3 class="drawer-title">{{ appName(detail?.executableName) || '加载中…' }}</h3>
        </div>
        <button class="btn btn-icon" title="关闭" @click="emit('close')">
          <i class="fas fa-xmark"></i>
        </button>
      </header>

      <div v-if="error" class="flash err"><i class="fas fa-triangle-exclamation"></i> {{ error }}</div>
      <p v-else-if="truncated" class="flash note">
        <i class="fas fa-circle-info"></i> 全部范围的应用详情仅统计最近 90 天
      </p>

      <div v-if="detail" class="drawer-body scroll-y">
        <div class="meta-grid">
          <div class="meta"><span class="meta-label">专注时长</span><b>{{ formatDuration(detail.summary.focusSeconds) }}</b></div>
          <div class="meta"><span class="meta-label">运行时长</span><b>{{ formatDuration(detail.summary.lifetimeSeconds) }}</b></div>
          <div class="meta"><span class="meta-label">专注占比</span><b>{{ formatPercent(detail.summary.focusRatio) }}</b></div>
          <div class="meta"><span class="meta-label">活跃天数</span><b>{{ detail.summary.activeDays }} 天</b></div>
          <div class="meta"><span class="meta-label">平均单次</span><b>{{ formatDuration(detail.summary.avgSessionFocusSeconds) }}</b></div>
          <div class="meta"><span class="meta-label">会话数</span><b>{{ detail.summary.sessionCount }}</b></div>
        </div>

        <section class="block">
          <h4>日趋势</h4>
          <div class="chart-box">
            <ActivityTrendChart :points="detail.series" />
          </div>
        </section>

        <section class="block">
          <h4>时段分布（专注）</h4>
          <div class="chart-box">
            <HourlyDistributionChart :data="detail.hourly" metric="focus" />
          </div>
        </section>

        <section class="block">
          <h4>Top 窗口</h4>
          <div v-if="detail.topWindows.length === 0" class="hint">暂无窗口记录</div>
          <ul v-else class="window-list">
            <li v-for="(w, i) in detail.topWindows" :key="i" class="window-item">
              <span class="window-title" :title="w.windowTitle || '(无标题)'">
                {{ w.windowTitle || '(无标题)' }}
              </span>
              <span class="window-time">{{ formatDuration(w.focusSeconds) }}</span>
            </li>
          </ul>
        </section>

        <section class="block">
          <h4>最近会话</h4>
          <div v-if="detail.recentSessions.length === 0" class="hint">暂无会话</div>
          <ul v-else class="session-list">
            <li v-for="s in detail.recentSessions" :key="s.id" class="session-item">
              <span class="session-time">
                {{ formatDateTime(s.start) }}<template v-if="s.end"> – {{ formatTime(s.end) }}</template>
              </span>
              <span class="session-meta">
                运行 {{ formatDurationCompact(s.lifetimeSeconds) }} · 专注
                {{ formatDurationCompact(s.focusSeconds) }}
              </span>
            </li>
          </ul>
        </section>
      </div>
      <div v-else-if="!error" class="hint pad">加载中…</div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { getAppDetail, type AppDetail } from '@/api/analytics'
import {
  appName,
  formatDateTime,
  formatDuration,
  formatDurationCompact,
  formatPercent,
  formatTime,
} from '@/utils/format'
import ActivityTrendChart from '@/components/charts/ActivityTrendChart.vue'
import HourlyDistributionChart from '@/components/charts/HourlyDistributionChart.vue'

const props = defineProps<{
  appId: number | null
  from: string
  to: string
  tz: number
  truncated?: boolean
}>()
const emit = defineEmits<{ (e: 'close'): void }>()

const detail = ref<AppDetail | null>(null)
const error = ref('')

watch(
  () => props.appId,
  async (id) => {
    detail.value = null
    error.value = ''
    if (id === null) return
    try {
      detail.value = await getAppDetail(id, { from: props.from, to: props.to, tz: props.tz })
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err?.response?.data?.detail || err?.message || '加载失败'
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.drawer-mask {
  position: fixed;
  inset: 0;
  z-index: 1100;
  background: rgba(2, 6, 23, 0.55);
  display: flex;
  justify-content: flex-end;
}
.drawer {
  width: min(560px, 94vw);
  height: 100%;
  display: flex;
  flex-direction: column;
  background: rgba(11, 18, 32, 0.94);
  border-left: 1px solid var(--border);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  box-shadow: var(--shadow-lg);
}
.drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--border);
}
.drawer-title {
  margin: 0;
  font-size: 1.05rem;
  color: var(--text-strong);
}
.drawer-body {
  padding: var(--sp-5);
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  overflow-y: auto;
}
.pad {
  padding: var(--sp-5);
}
.flash.note {
  margin: var(--sp-4) var(--sp-5) 0;
  background: rgba(79, 156, 249, 0.1);
  border: 1px solid var(--accent-border);
  color: #bfdbfe;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-3);
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface-soft);
}
.meta-label {
  font-size: 0.7rem;
  color: var(--text-faint);
}
.meta b {
  font-size: 0.95rem;
  color: var(--text-strong);
}

.block h4 {
  margin: 0 0 var(--sp-2);
  font-size: 0.85rem;
  color: var(--text);
  font-weight: 600;
}
.chart-box {
  height: 240px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface-soft);
  padding: 0.25rem;
}

.window-list,
.session-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.window-item,
.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: 0.5rem 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 0.82rem;
}
.window-title {
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.window-time,
.session-meta {
  color: var(--text-faint);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  flex-shrink: 0;
}
.session-time {
  color: var(--text-muted);
  font-size: 0.75rem;
}
</style>
