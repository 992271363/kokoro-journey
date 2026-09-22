<template>
  <div ref="el" class="chart"></div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import { useEcharts } from '@/composables/useEcharts'
import { formatDurationCompact } from '@/utils/format'
import { CHART_AXIS, CHART_SPLIT, axisLabel, tooltipStyle } from './base'

const props = defineProps<{ grid: number[][] }>()

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const el = ref<HTMLElement | null>(null)

const option = computed<EChartsCoreOption>(() => {
  const data: [number, number, number][] = []
  let max = 0
  props.grid.forEach((row, day) => {
    row.forEach((value, hour) => {
      data.push([hour, day, value])
      max = Math.max(max, value)
    })
  })
  return {
    tooltip: {
      ...tooltipStyle,
      formatter: (p: unknown) => {
        const item = p as { value: [number, number, number] }
        return `${WEEKDAYS[item.value[1]]} ${item.value[0]}:00<br/>专注 ${formatDurationCompact(item.value[2])}`
      },
    },
    grid: { left: 8, right: 12, top: 8, bottom: 56, containLabel: true },
    xAxis: {
      type: 'category',
      data: Array.from({ length: 24 }, (_, h) => `${h}`),
      splitArea: { show: true, areaStyle: { color: ['transparent', 'rgba(255,255,255,0.02)'] } },
      axisLine: { lineStyle: { color: CHART_AXIS } },
      axisLabel,
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: WEEKDAYS,
      inverse: true,
      splitArea: { show: true, areaStyle: { color: ['transparent', 'rgba(255,255,255,0.02)'] } },
      axisLine: { lineStyle: { color: CHART_AXIS } },
      axisLabel,
      axisTick: { show: false },
    },
    visualMap: {
      min: 0,
      max: Math.max(1, max),
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemWidth: 12,
      itemHeight: 90,
      textStyle: { color: '#64748b', fontSize: 11 },
      inRange: { color: ['rgba(79,156,249,0.08)', 'rgba(79,156,249,0.45)', '#4f9cf9'] },
      formatter: (v: unknown) => formatDurationCompact(Number(v)),
    },
    series: [
      {
        name: '专注',
        type: 'heatmap',
        data,
        itemStyle: { borderColor: 'rgba(2,6,23,0.6)', borderWidth: 1 },
        emphasis: { itemStyle: { borderColor: '#e2e8f0', borderWidth: 1 } },
      },
    ],
    splitLine: { lineStyle: { color: CHART_SPLIT } },
  }
})

useEcharts(el, option)
</script>

<style scoped>
.chart {
  width: 100%;
  height: 100%;
  min-height: 300px;
}
</style>
