<template>
  <div ref="el" class="chart"></div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import { useEcharts } from '@/composables/useEcharts'
import { shortDate, formatDurationCompact } from '@/utils/format'
import type { TimeseriesPoint } from '@/api/analytics'
import {
  CHART_AXIS,
  CHART_FOCUS,
  CHART_LIFETIME,
  CHART_SPLIT,
  CHART_TEXT,
  axisLabel,
  baseGrid,
  tooltipStyle,
} from './base'

const props = defineProps<{ points: TimeseriesPoint[] }>()

const el = ref<HTMLElement | null>(null)

const option = computed<EChartsCoreOption>(() => ({
  tooltip: {
    trigger: 'axis',
    ...tooltipStyle,
    valueFormatter: (v: unknown) => formatDurationCompact(Number(v)),
  },
  legend: {
    data: ['专注', '运行'],
    top: 0,
    right: 0,
    textStyle: { color: CHART_TEXT, fontSize: 11 },
    itemWidth: 12,
    itemHeight: 8,
  },
  grid: baseGrid(),
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: props.points.map((p) => shortDate(p.date)),
    axisLine: { lineStyle: { color: CHART_AXIS } },
    axisLabel,
    axisTick: { show: false },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: CHART_SPLIT } },
    axisLabel: { ...axisLabel, formatter: (v: number) => formatDurationCompact(v) },
  },
  series: [
    {
      name: '专注',
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: props.points.map((p) => p.focusSeconds),
      lineStyle: { color: CHART_FOCUS, width: 2 },
      itemStyle: { color: CHART_FOCUS },
      areaStyle: { color: 'rgba(79, 156, 249, 0.18)' },
    },
    {
      name: '运行',
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: props.points.map((p) => p.lifetimeSeconds),
      lineStyle: { color: CHART_LIFETIME, width: 2 },
      itemStyle: { color: CHART_LIFETIME },
      areaStyle: { color: 'rgba(52, 200, 138, 0.12)' },
    },
  ],
}))

useEcharts(el, option)
</script>

<style scoped>
.chart {
  width: 100%;
  height: 100%;
  min-height: 240px;
}
</style>
