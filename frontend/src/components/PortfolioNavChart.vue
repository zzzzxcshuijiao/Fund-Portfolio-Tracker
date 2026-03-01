<template>
  <div class="portfolio-nav-container">
    <v-chart v-if="hasData" class="chart" :option="chartOption" autoresize />
    <el-empty v-else description="暂无数据，请先在设置页生成今日快照" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, TooltipComponent, GridComponent, DataZoomComponent, CanvasRenderer])

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const hasData = computed(() => props.data.some((d) => d.total_market_value > 0))

const chartOption = computed(() => {
  const dates = props.data.map((d) => d.date)
  const mvValues = props.data.map((d) => Number(d.total_market_value))

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = params[0]
        const val = Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
        return `${p.axisValue}<br/>资产总值: <b>￥${val}</b>`
      },
    },
    grid: { left: 80, right: 20, top: 20, bottom: 60 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { rotate: 30, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: (val) => '￥' + (val / 10000).toFixed(1) + '万',
      },
      splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
    },
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        name: '资产总值',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        showSymbol: props.data.length <= 30,
        lineStyle: { width: 2.5, color: '#409eff' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(64,158,255,0.25)' },
              { offset: 1, color: 'rgba(64,158,255,0.02)' },
            ],
          },
        },
        data: mvValues,
      },
    ],
  }
})
</script>

<style scoped>
.portfolio-nav-container {
  width: 100%;
  height: 350px;
}

.chart {
  width: 100%;
  height: 100%;
}
</style>
