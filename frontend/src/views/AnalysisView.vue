<template>
  <div class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Analysis</p>
        <h1 class="page-title">分析</h1>
        <p class="sub">{{ from }} ~ {{ to }} · 历史活动分析</p>
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
    <p v-if="activityTruncated" class="flash note">
      <i class="fas fa-circle-info"></i> 全部范围的时段分析仅统计最近 90 天
    </p>

    <section class="panel">
      <div class="panel-header">
        <h2 class="panel-title">时段分布</h2>
        <div class="seg">
          <button
            v-for="m in metrics"
            :key="m.key"
            class="seg-btn"
            :class="{ active: metric === m.key }"
            @click="setMetric(m.key)"
          >
            {{ m.label }}
          </button>
        </div>
      </div>
      <div class="chart-box">
        <div v-if="loadingHourly" class="hint pad">加载中…</div>
        <HourlyDistributionChart v-else :data="hourly" :metric="metric" />
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2 class="panel-title">7×24 专注热力图</h2>
        <span class="panel-badge">周一 → 周日</span>
      </div>
      <div class="chart-box heat">
        <div v-if="loadingHeatmap" class="hint pad">加载中…</div>
        <WeeklyHeatmapChart v-else :grid="heatmap" />
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2 class="panel-title">应用对比</h2>
        <span class="panel-badge">{{ apps.length }} 个</span>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>应用</th>
              <th class="num">高峰时段</th>
              <th class="num">专注</th>
              <th class="num">活跃天数</th>
              <th class="num">平均单次</th>
              <th class="num">专注占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loadingApps">
              <td colspan="6" class="hint pad">加载中…</td>
            </tr>
            <tr v-else-if="apps.length === 0">
              <td colspan="6" class="hint pad">该范围暂无数据</td>
            </tr>
            <tr v-for="app in apps" v-else :key="app.appId">
              <td class="cell-name" :title="app.executableName">{{ appName(app.executableName) }}</td>
              <td class="num">{{ peakLabel(app.peakHour) }}</td>
              <td class="num">{{ formatDuration(app.focusSeconds) }}</td>
              <td class="num">{{ app.activeDays }} 天</td>
              <td class="num">{{ formatDuration(app.avgSessionFocusSeconds) }}</td>
              <td class="num">{{ formatPercent(app.focusRatio) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useTimeRange } from '@/composables/useTimeRange'
import {
  getApps,
  getHeatmap,
  getHourly,
  localTzMinutes,
  type AppRankItem,
} from '@/api/analytics'
import { appName, formatDuration, formatPercent } from '@/utils/format'
import TimeRangePicker from '@/components/TimeRangePicker.vue'
import HourlyDistributionChart from '@/components/charts/HourlyDistributionChart.vue'
import WeeklyHeatmapChart from '@/components/charts/WeeklyHeatmapChart.vue'

type Metric = 'focus' | 'opens' | 'closes'

const tz = localTzMinutes()
const { preset, from, to, activityParams, activityTruncated, setPreset, setCustom } =
  useTimeRange('last30')

const metrics: { key: Metric; label: string }[] = [
  { key: 'focus', label: '专注' },
  { key: 'opens', label: '打开' },
  { key: 'closes', label: '关闭' },
]
const metric = ref<Metric>('focus')

const hourly = ref<number[]>(Array.from({ length: 24 }, () => 0))
const heatmap = ref<number[][]>(
  Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0)),
)
const apps = ref<AppRankItem[]>([])
const loadingHourly = ref(false)
const loadingHeatmap = ref(false)
const loadingApps = ref(false)
const error = ref('')

const paramsWithTz = computed(() => ({ ...activityParams.value, tz }))

function reportError(e: unknown, fallback: string) {
  const err = e as { response?: { data?: { detail?: string } }; message?: string }
  error.value = err?.response?.data?.detail || err?.message || fallback
}

function peakLabel(hour: number | null): string {
  if (hour === null || hour === undefined) return '—'
  return `${hour}:00–${hour + 1}:00`
}

async function loadHourly() {
  loadingHourly.value = true
  try {
    hourly.value = await getHourly({ ...paramsWithTz.value, metric: metric.value })
  } catch (e) {
    reportError(e, '无法加载时段分布')
  } finally {
    loadingHourly.value = false
  }
}

async function loadHeatmap() {
  loadingHeatmap.value = true
  try {
    heatmap.value = await getHeatmap(paramsWithTz.value)
  } catch (e) {
    reportError(e, '无法加载热力图')
  } finally {
    loadingHeatmap.value = false
  }
}

async function loadApps() {
  loadingApps.value = true
  try {
    const res = await getApps({ ...paramsWithTz.value, include: 'peak', page: 1, pageSize: 50 })
    apps.value = res.items
  } catch (e) {
    reportError(e, '无法加载应用对比')
  } finally {
    loadingApps.value = false
  }
}

function setMetric(next: Metric) {
  if (next === metric.value) return
  metric.value = next
  void loadHourly()
}

function reloadAll() {
  error.value = ''
  void loadHourly()
  void loadHeatmap()
  void loadApps()
}

watch(() => [from.value, to.value], reloadAll)

onMounted(reloadAll)
</script>

<style scoped>
.sub {
  margin: var(--sp-1) 0 0;
  font-size: 0.88rem;
  color: var(--text-muted);
}

.flash.note {
  background: rgba(79, 156, 249, 0.1);
  border: 1px solid var(--accent-border);
  color: #bfdbfe;
}

.chart-box {
  height: 260px;
  padding: var(--sp-3);
}
.chart-box.heat {
  height: 340px;
}
.pad {
  padding: var(--sp-5);
}

.seg {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: rgba(2, 6, 23, 0.4);
}
.seg-btn {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.78rem;
  padding: 0.35rem 0.7rem;
  border-radius: 6px;
  cursor: pointer;
}
.seg-btn:hover {
  color: var(--text);
}
.seg-btn.active {
  background: var(--accent-soft);
  color: #bfdbfe;
}

.table-wrap {
  overflow-x: auto;
}
.num {
  text-align: right;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: var(--text-muted);
}
.cell-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.panel + .panel {
  margin-top: var(--sp-4);
}

@media (max-width: 560px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--sp-2);
  }
}
</style>
