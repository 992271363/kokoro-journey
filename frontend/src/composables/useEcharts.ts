// frontend/src/composables/useEcharts.ts
// ECharts 按需注册 + 生命周期（init/resize/dispose），让页面只关心 option。
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, HeatmapChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsCoreOption } from 'echarts/core'

echarts.use([
  LineChart,
  BarChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  CanvasRenderer,
])

/** 仅声明我们实际使用到的方法，避免与 echarts 的实例类型纠缠。 */
export interface ChartHandle {
  setOption(option: EChartsCoreOption, notMerge?: boolean): void
  resize(): void
  dispose(): void
}

export function useEcharts(
  el: Ref<HTMLElement | null>,
  option: Ref<EChartsCoreOption>,
  onInit?: (chart: ChartHandle) => void,
) {
  const chart = ref<ChartHandle | null>(null)
  let observer: ResizeObserver | null = null

  onMounted(() => {
    if (!el.value) return
    const instance = echarts.init(el.value) as unknown as ChartHandle
    chart.value = instance
    instance.setOption(option.value)
    onInit?.(instance)
    observer = new ResizeObserver(() => instance.resize())
    observer.observe(el.value)
  })

  watch(option, (next) => {
    chart.value?.setOption(next, true)
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
    chart.value?.dispose()
    chart.value = null
  })

  return { chart }
}
