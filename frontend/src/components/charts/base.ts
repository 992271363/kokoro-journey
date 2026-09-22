// frontend/src/components/charts/base.ts
// 图表共享的暗色主题常量与基础 option 片段（与 theme.css 令牌保持视觉一致）。
import type { EChartsCoreOption } from 'echarts/core'

export const CHART_TEXT = '#94a3b8'
export const CHART_TEXT_FAINT = '#64748b'
export const CHART_AXIS = 'rgba(255, 255, 255, 0.10)'
export const CHART_SPLIT = 'rgba(255, 255, 255, 0.06)'
export const CHART_FOCUS = '#4f9cf9'
export const CHART_LIFETIME = '#34c88a'
export const CHART_TOOLTIP_BG = 'rgba(15, 23, 42, 0.94)'

export const tooltipStyle = {
  backgroundColor: CHART_TOOLTIP_BG,
  borderColor: CHART_AXIS,
  textStyle: { color: '#e2e8f0', fontSize: 12 },
}

export function baseGrid(): EChartsCoreOption['grid'] {
  return { left: 8, right: 12, top: 36, bottom: 8, containLabel: true }
}

export const axisLabel = { color: CHART_TEXT_FAINT, fontSize: 11 }
