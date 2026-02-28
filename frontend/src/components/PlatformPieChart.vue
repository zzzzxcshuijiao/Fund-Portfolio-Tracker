<template>
  <div class="pie-chart-container">
    <v-chart v-if="data.length" class="chart" :option="chartOption" autoresize />
    <el-empty v-else description="暂无平台分布数据" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([PieChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const chartOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: (params) => {
      const item = props.data.find((d) => d.platform === params.name)
      const pnl = item && item.daily_pnl != null ? Number(item.daily_pnl) : null
      const pnlStr = pnl != null
        ? `<br/>日涨跌额: <span style="color:${pnl >= 0 ? '#f56c6c' : '#67c23a'}">￥${pnl.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>`
        : ''
      return `${params.name}<br/>市值: ￥${Number(params.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}${pnlStr}<br/>占比: ${params.percent}%`
    },
  },
  legend: {
    type: 'scroll',
    orient: 'vertical',
    right: 10,
    top: 20,
    bottom: 20,
  },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['35%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: {
        borderRadius: 6,
        borderColor: '#fff',
        borderWidth: 2,
      },
      label: {
        show: false,
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 14,
          fontWeight: 'bold',
        },
      },
      data: props.data.map((item) => ({
        name: item.platform,
        value: Number(item.market_value),
      })),
    },
  ],
}))
</script>

<style scoped>
.pie-chart-container {
  width: 100%;
  height: 350px;
}

.chart {
  width: 100%;
  height: 100%;
}
</style>
