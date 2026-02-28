<template>
  <div class="nav-history-container">
    <v-chart v-if="data.length" class="chart" :option="chartOption" autoresize />
    <el-empty v-else description="暂无历史净值数据" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
  MarkPointComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, TitleComponent, TooltipComponent, GridComponent, DataZoomComponent, MarkPointComponent, CanvasRenderer])

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const chartOption = computed(() => {
  const dates = props.data.map((d) => d.date)
  const values = props.data.map((d) => Number(d.unit_nav))

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = params[0]
        const item = props.data[p.dataIndex]
        let result = `${p.axisValue}<br/>`
        result += `${p.marker} 单位净值: ${Number(p.value).toFixed(4)}<br/>`
        if (item && item.change_pct != null) {
          const pct = Number(item.change_pct)
          const color = pct >= 0 ? '#f56c6c' : '#67c23a'
          result += `<span style="color:${color}">涨跌: ${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</span>`
        }
        return result
      },
    },
    grid: {
      left: 60,
      right: 20,
      top: 20,
      bottom: 60,
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLabel: {
        rotate: 30,
        fontSize: 11,
      },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        formatter: (val) => val.toFixed(4),
      },
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', start: 0, end: 100 },
    ],
    series: [
      {
        type: 'line',
        data: values,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 2,
          color: '#409eff',
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(64,158,255,0.3)' },
              { offset: 1, color: 'rgba(64,158,255,0.02)' },
            ],
          },
        },
        markPoint: {
          data: [
            { type: 'max', name: '最高' },
            { type: 'min', name: '最低' },
          ],
          label: { formatter: (p) => Number(p.value).toFixed(4) },
        },
      },
    ],
  }
})
</script>

<style scoped>
.nav-history-container {
  width: 100%;
  height: 400px;
}

.chart {
  width: 100%;
  height: 100%;
}
</style>
