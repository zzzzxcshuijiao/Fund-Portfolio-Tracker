<template>
  <div class="daily-pnl-container">
    <v-chart v-if="data.length" class="chart" :option="chartOption" autoresize />
    <el-empty v-else description="暂无日收益数据，需积累快照" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  DataZoomComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, LineChart, TitleComponent, TooltipComponent, GridComponent, DataZoomComponent, CanvasRenderer])

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const chartOption = computed(() => {
  const dates = props.data.map((d) => d.date)
  const pnlValues = props.data.map((d) => d.daily_pnl ? Number(d.daily_pnl) : 0)
  const mvValues = props.data.map((d) => Number(d.total_market_value))

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params) => {
        let result = `${params[0].axisValue}<br/>`
        params.forEach(p => {
          const val = Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
          result += `${p.marker} ${p.seriesName}: ￥${val}<br/>`
        })
        return result
      },
    },
    grid: {
      left: 60,
      right: 60,
      top: 20,
      bottom: 60,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        rotate: 30,
        fontSize: 11,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '日盈亏',
        axisLabel: { formatter: (val) => '￥' + val.toFixed(0) },
      },
      {
        type: 'value',
        name: '总市值',
        axisLabel: { formatter: (val) => `${(val / 10000).toFixed(1)}万` },
      },
    ],
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
    ],
    series: [
      {
        name: '日盈亏',
        type: 'bar',
        data: pnlValues.map((v) => ({
          value: v,
          itemStyle: {
            color: v >= 0 ? '#f56c6c' : '#67c23a',
          },
        })),
        barMaxWidth: 30,
      },
      {
        name: '总市值',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: '#409eff' },
        data: mvValues,
      },
    ],
  }
})
</script>

<style scoped>
.daily-pnl-container {
  width: 100%;
  height: 350px;
}

.chart {
  width: 100%;
  height: 100%;
}
</style>
