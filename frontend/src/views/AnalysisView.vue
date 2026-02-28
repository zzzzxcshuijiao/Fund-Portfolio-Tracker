<template>
  <div class="analysis-view">
    <h2 class="page-title">投资分析</h2>

    <!-- Period Selector -->
    <el-card shadow="hover" class="selector-card">
      <el-row :gutter="16" align="middle">
        <el-col :span="10">
          <el-select
            v-model="selectedPeriodIdx"
            placeholder="选择分析期间"
            style="width: 100%"
            @change="handlePeriodChange"
          >
            <el-option
              v-for="(p, idx) in periods"
              :key="idx"
              :label="`${p.start_label} → ${p.end_label}`"
              :value="idx"
            />
          </el-select>
        </el-col>
        <el-col :span="14">
          <div v-if="selectedPeriod" class="period-summary">
            <span>交易日: {{ selectedPeriod.trading_days }} 天</span>
            <span class="divider">|</span>
            <span>
              期间总盈亏:
              <span :class="pnlClass(selectedPeriod.total_pnl)">
                ￥{{ formatNumber(selectedPeriod.total_pnl) }}
              </span>
            </span>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <template v-if="selectedPeriod">
      <!-- Summary Cards -->
      <el-row :gutter="16" class="summary-row">
        <el-col :span="8">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-label">期间总盈亏</div>
            <div class="stat-value" :class="pnlClass(selectedPeriod.total_pnl)">
              ￥{{ formatNumber(selectedPeriod.total_pnl) }}
            </div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-label">日均盈亏</div>
            <div class="stat-value" :class="pnlClass(avgDailyPnl)">
              ￥{{ formatNumber(avgDailyPnl) }}
            </div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-label">交易日数</div>
            <div class="stat-value">{{ selectedPeriod.trading_days }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Daily PnL Chart -->
      <el-card shadow="hover" class="chart-card">
        <template #header>
          <span>日收益趋势</span>
        </template>
        <div ref="chartRef" class="chart-container" v-loading="chartLoading"></div>
      </el-card>

      <!-- Fund PnL Ranking -->
      <el-card shadow="hover" class="ranking-card">
        <template #header>
          <span>基金盈亏排行</span>
        </template>
        <el-table :data="fundPnlList" stripe v-loading="fundLoading" max-height="600">
          <el-table-column prop="fund_code" label="基金代码" width="100" />
          <el-table-column prop="fund_name" label="基金名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="platform" label="平台" width="120" show-overflow-tooltip />
          <el-table-column label="份额" width="120" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.shares) }}
            </template>
          </el-table-column>
          <el-table-column label="期初市值" width="130" align="right">
            <template #default="{ row }">
              ￥{{ formatNumber(row.start_mv) }}
            </template>
          </el-table-column>
          <el-table-column label="期末市值" width="130" align="right">
            <template #default="{ row }">
              ￥{{ formatNumber(row.end_mv) }}
            </template>
          </el-table-column>
          <el-table-column label="期间盈亏" width="130" align="right" sortable sort-by="period_pnl">
            <template #default="{ row }">
              <span :class="pnlClass(row.period_pnl)">
                ￥{{ formatNumber(row.period_pnl) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="盈亏率" width="100" align="right" sortable sort-by="period_pnl_pct">
            <template #default="{ row }">
              <span :class="pnlClass(row.period_pnl_pct)">
                {{ row.period_pnl_pct != null ? Number(row.period_pnl_pct).toFixed(2) + '%' : '--' }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <el-empty v-else-if="!periodsLoading && periods.length === 0" description="暂无分析数据，需要至少两次导入记录和每日快照数据" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { getAnalysisPeriods, getPeriodDetail, getFundPnl } from '../api/index.js'

const periods = ref([])
const periodsLoading = ref(false)
const selectedPeriodIdx = ref(null)
const dailyData = ref([])
const fundPnlList = ref([])
const chartLoading = ref(false)
const fundLoading = ref(false)
const chartRef = ref(null)
let chartInstance = null

const selectedPeriod = computed(() => {
  if (selectedPeriodIdx.value == null) return null
  return periods.value[selectedPeriodIdx.value]
})

const avgDailyPnl = computed(() => {
  const p = selectedPeriod.value
  if (!p || !p.total_pnl || !p.trading_days) return null
  return Number(p.total_pnl) / p.trading_days
})

function formatNumber(val) {
  if (val == null) return '--'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pnlClass(val) {
  if (val == null) return ''
  return Number(val) > 0 ? 'text-profit' : Number(val) < 0 ? 'text-loss' : ''
}

async function loadPeriods() {
  periodsLoading.value = true
  try {
    periods.value = await getAnalysisPeriods()
    // Auto-select latest period
    if (periods.value.length > 0) {
      selectedPeriodIdx.value = periods.value.length - 1
      handlePeriodChange()
    }
  } catch {
    // Errors handled by interceptor
  } finally {
    periodsLoading.value = false
  }
}

async function handlePeriodChange() {
  const p = selectedPeriod.value
  if (!p) return

  // Load period detail and fund PnL in parallel
  chartLoading.value = true
  fundLoading.value = true

  const params = { start_date: p.start_date, end_date: p.end_date }

  try {
    const [detail, funds] = await Promise.all([
      getPeriodDetail(params),
      getFundPnl(params),
    ])
    dailyData.value = detail
    fundPnlList.value = funds
    await nextTick()
    renderChart()
  } catch {
    // Errors handled by interceptor
  } finally {
    chartLoading.value = false
    fundLoading.value = false
  }
}

function renderChart() {
  if (!chartRef.value) return

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const dates = dailyData.value.map(d => d.pnl_date)
  const pnlValues = dailyData.value.map(d => d.total_pnl ? Number(d.total_pnl) : 0)

  // Cumulative PnL
  const cumPnl = []
  let sum = 0
  for (const v of pnlValues) {
    sum += v
    cumPnl.push(Number(sum.toFixed(2)))
  }

  chartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const date = params[0].axisValue
        let html = `<div style="font-weight:600">${date}</div>`
        for (const p of params) {
          const val = Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
          html += `<div>${p.marker} ${p.seriesName}: ￥${val}</div>`
        }
        return html
      },
    },
    legend: {
      data: ['日盈亏', '累计盈亏'],
      bottom: 0,
    },
    grid: {
      top: 20,
      left: 60,
      right: 60,
      bottom: 40,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 11 },
    },
    yAxis: [
      {
        type: 'value',
        name: '日盈亏',
        axisLabel: { formatter: v => (v / 1).toFixed(0) },
      },
      {
        type: 'value',
        name: '累计盈亏',
        axisLabel: { formatter: v => (v / 1).toFixed(0) },
      },
    ],
    series: [
      {
        name: '日盈亏',
        type: 'bar',
        data: pnlValues,
        itemStyle: {
          color(params) {
            return params.value >= 0 ? '#f56c6c' : '#67c23a'
          },
        },
      },
      {
        name: '累计盈亏',
        type: 'line',
        yAxisIndex: 1,
        data: cumPnl,
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#409eff' },
      },
    ],
  })
}

// Handle resize
function handleResize() {
  chartInstance?.resize()
}

onMounted(() => {
  loadPeriods()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})
</script>

<style scoped>
.analysis-view {
  padding: 4px;
}

.page-title {
  margin: 0 0 20px 0;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.selector-card {
  margin-bottom: 16px;
}

.period-summary {
  color: #606266;
  font-size: 14px;
  line-height: 32px;
}

.period-summary .divider {
  margin: 0 12px;
  color: #dcdfe6;
}

.summary-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
}

.stat-label {
  color: #909399;
  font-size: 13px;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.chart-card {
  margin-bottom: 16px;
}

.chart-container {
  height: 350px;
  width: 100%;
}

.ranking-card {
  margin-bottom: 20px;
}

.text-profit {
  color: #f56c6c;
  font-weight: 500;
}

.text-loss {
  color: #67c23a;
  font-weight: 500;
}
</style>
