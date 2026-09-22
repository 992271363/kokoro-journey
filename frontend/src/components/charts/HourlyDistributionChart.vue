<template>
  <div ref="el" class="chart"></div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import { useEcharts } from '@/composables/useEcharts'
import { formatDurationCompact } from '@/utils/format'
import {
  CHART_AXIS,
  CHART_FOCUS,
  CHART_SPLIT,
  axisLabel,
  baseGrid,
  tooltipStyle,
} from './base'

const props = withDefaults(
  defineProps<{ data: number[]; metric?: 'focus' | 'opens' | 'closes' }>(),
  { metric: 'focus' },
)

const el = ref<HTMLElement | null>(null)

const unitLabel = computed(() =>
  props.metric === 'focus' ? '专注' : props.metric === 'opens' ? '打开' : '关闭',
)

const option = computed<EChartsCoreOption>(() => ({
  tooltip: {
    trigger: 'axis',
    ...tooltipStyle,
    valueFormatter:
      props.metric === 'focus'
        ? (v: unknown) => formatDurationCompact(Number(v))
        : (v: unknown) => `${v} 次`,
  },
  grid: baseGrid(),
  xAxis: {
    type: 'category',
    data: Array.from({ length: 24 }, (_, h) => `${h}`),
    axisLine: { lineStyle: { color: CHART_AXIS } },
    axisLabel,
    axisTick: { show: false },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: CHART_SPLIT } },
    axisLabel: {
      ...axisLabel,
      formatter:
        props.metric === 'focus' ? (v: number) => formatDurationCompact(v) : (v: number) => `${v}`,
    },
  },
  series: [
    {
      name: unitLabel.value,
      type: 'bar',
      data: props.data,
      barMaxWidth: 18,
      itemStyle: { color: CHART_FOCUS, borderRadius: [3, 3, 0, 0] },
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
