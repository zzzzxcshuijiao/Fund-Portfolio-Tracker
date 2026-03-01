<template>
  <div class="calendar-view">
    <h2 class="page-title">收益日历</h2>

    <el-row :gutter="16">
      <!-- Left: Summary card -->
      <el-col :span="6">
        <el-card shadow="hover" class="summary-card">
          <template #header>
            <span class="summary-title">月度汇总</span>
          </template>
          <div v-if="loading" class="summary-loading">
            <el-skeleton :rows="5" animated />
          </div>
          <div v-else-if="data" class="summary-body">
            <div class="summary-item">
              <span class="summary-label">月末资产</span>
              <span class="summary-value">
                {{ monthEndMv != null ? '¥' + formatNum(monthEndMv) : '-' }}
              </span>
            </div>
            <div class="summary-item">
              <span class="summary-label">月累计盈亏</span>
              <span class="summary-value" :class="pnlClass(data.summary.total_pnl)">
                {{ formatMoney(data.summary.total_pnl) }}
              </span>
            </div>
            <div class="summary-item">
              <span class="summary-label">交易日</span>
              <span class="summary-value">{{ data.summary.trading_days }} 天</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">日均盈亏</span>
              <span class="summary-value" :class="pnlClass(data.summary.avg_daily_pnl)">
                {{ formatMoney(data.summary.avg_daily_pnl) }}
              </span>
            </div>
            <div v-if="data.summary.best_day" class="summary-item">
              <span class="summary-label">最佳单日</span>
              <span class="summary-value pnl-positive">
                {{ data.summary.best_day.date.slice(5) }}
                {{ formatMoney(data.summary.best_day.daily_pnl) }}
              </span>
            </div>
            <div v-if="data.summary.worst_day" class="summary-item">
              <span class="summary-label">最差单日</span>
              <span class="summary-value pnl-negative">
                {{ data.summary.worst_day.date.slice(5) }}
                {{ formatMoney(data.summary.worst_day.daily_pnl) }}
              </span>
            </div>
          </div>
          <div v-else class="summary-empty">暂无数据</div>
        </el-card>
      </el-col>

      <!-- Right: Calendar grid -->
      <el-col :span="18">
        <el-card shadow="hover" class="calendar-card">
          <!-- Month navigation -->
          <div class="month-nav">
            <el-button :icon="ArrowLeft" text @click="prevMonth" />
            <span class="month-label">{{ year }}年{{ month }}月</span>
            <el-button :icon="ArrowRight" text @click="nextMonth" />
            <el-button size="small" style="margin-left: 12px" @click="goToday">今天</el-button>
          </div>

          <!-- Calendar grid -->
          <div v-loading="loading" class="calendar-grid">
            <!-- Weekday headers -->
            <div class="weekday-header" v-for="w in weekdays" :key="w">{{ w }}</div>

            <!-- Day cells -->
            <div
              v-for="(cell, idx) in calendarCells"
              :key="idx"
              class="day-cell"
              :class="cellClass(cell)"
              @click="cell.day ? selectDate(cell) : null"
            >
              <template v-if="cell.day">
                <div class="day-number">{{ cell.day }}</div>
                <div v-if="cell.mv !== null" class="day-mv">{{ formatMv(cell.mv) }}</div>
                <div v-if="cell.pnl !== null" class="day-pnl" :class="pnlClass(cell.pnl)">
                  {{ formatCompact(cell.pnl) }}
                </div>
              </template>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Day detail panel -->
    <el-card v-if="selectedDate" shadow="hover" class="detail-card">
      <template #header>
        <span>{{ selectedDate }} 基金收益明细</span>
      </template>
      <el-table
        v-loading="detailLoading"
        :data="dayDetails"
        stripe
        size="small"
        :default-sort="{ prop: 'daily_pnl', order: 'descending' }"
      >
        <el-table-column prop="fund_code" label="代码" width="90" />
        <el-table-column prop="fund_name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="100" show-overflow-tooltip />
        <el-table-column prop="shares" label="份额" width="110" align="right">
          <template #default="{ row }">{{ formatNum(row.shares) }}</template>
        </el-table-column>
        <el-table-column prop="prev_nav" label="前日净值" width="100" align="right">
          <template #default="{ row }">{{ row.prev_nav ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="nav" label="当日净值" width="100" align="right">
          <template #default="{ row }">{{ row.nav ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="daily_pnl" label="盈亏" width="120" align="right" sortable>
          <template #default="{ row }">
            <span v-if="row.daily_pnl !== null" :class="pnlClass(row.daily_pnl)">
              {{ formatMoney(row.daily_pnl) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="daily_pnl_pct" label="涨跌幅" width="100" align="right" sortable>
          <template #default="{ row }">
            <span v-if="row.daily_pnl_pct !== null" :class="pnlClass(row.daily_pnl_pct)">
              {{ row.daily_pnl_pct > 0 ? '+' : '' }}{{ row.daily_pnl_pct }}%
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="market_value" label="市值" width="120" align="right">
          <template #default="{ row }">
            {{ row.market_value ? formatMoney(row.market_value) : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { getCalendarMonth, getCalendarDayDetail } from '../api'

const weekdays = ['一', '二', '三', '四', '五', '六', '日']

const now = new Date()
const year = ref(now.getFullYear())
const month = ref(now.getMonth() + 1)

const loading = ref(false)
const data = ref(null)

const selectedDate = ref(null)
const detailLoading = ref(false)
const dayDetails = ref([])

// Build a map for quick lookup: "YYYY-MM-DD" -> day data
const pnlMap = computed(() => {
  const map = {}
  if (data.value?.daily_data) {
    for (const d of data.value.daily_data) {
      map[d.date] = d
    }
  }
  return map
})

// Last trading day's market value in this month
const monthEndMv = computed(() => {
  if (!data.value?.daily_data?.length) return null
  const sorted = [...data.value.daily_data].filter(d => d.market_value != null)
  if (!sorted.length) return null
  return Number(sorted[sorted.length - 1].market_value)
})

// Generate calendar cells (6 rows x 7 cols)
const calendarCells = computed(() => {
  const cells = []
  const firstDay = new Date(year.value, month.value - 1, 1)
  // Monday=0 ... Sunday=6
  let startWeekday = firstDay.getDay() - 1
  if (startWeekday < 0) startWeekday = 6

  const daysInMonth = new Date(year.value, month.value, 0).getDate()

  // Leading empty cells
  for (let i = 0; i < startWeekday; i++) {
    cells.push({ day: null, pnl: null, pnlPct: null, mv: null, dateStr: null })
  }

  // Day cells
  for (let d = 1; d <= daysInMonth; d++) {
    const mm = String(month.value).padStart(2, '0')
    const dd = String(d).padStart(2, '0')
    const dateStr = `${year.value}-${mm}-${dd}`
    const dayData = pnlMap.value[dateStr]
    cells.push({
      day: d,
      dateStr,
      pnl: dayData?.daily_pnl != null ? Number(dayData.daily_pnl) : null,
      pnlPct: dayData?.daily_pnl_pct != null ? Number(dayData.daily_pnl_pct) : null,
      mv: dayData?.market_value != null ? Number(dayData.market_value) : null,
      isTrading: !!dayData,
    })
  }

  // Trailing empty cells to fill the grid
  while (cells.length % 7 !== 0) {
    cells.push({ day: null, pnl: null, pnlPct: null, mv: null, dateStr: null })
  }

  return cells
})

async function fetchMonth() {
  loading.value = true
  try {
    data.value = await getCalendarMonth({ year: year.value, month: month.value })
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

async function fetchDayDetail(dateStr) {
  detailLoading.value = true
  try {
    dayDetails.value = await getCalendarDayDetail(dateStr)
  } catch {
    dayDetails.value = []
  } finally {
    detailLoading.value = false
  }
}

function selectDate(cell) {
  if (!cell.dateStr) return
  selectedDate.value = cell.dateStr
  fetchDayDetail(cell.dateStr)
}

function prevMonth() {
  if (month.value === 1) {
    year.value--
    month.value = 12
  } else {
    month.value--
  }
}

function nextMonth() {
  if (month.value === 12) {
    year.value++
    month.value = 1
  } else {
    month.value++
  }
}

function goToday() {
  const today = new Date()
  year.value = today.getFullYear()
  month.value = today.getMonth() + 1
}

// Watch month/year changes
watch([year, month], () => {
  selectedDate.value = null
  dayDetails.value = []
  fetchMonth()
})

onMounted(fetchMonth)

// --- Formatters ---

function pnlClass(val) {
  if (val == null) return ''
  const n = Number(val)
  if (n > 0) return 'pnl-positive'
  if (n < 0) return 'pnl-negative'
  return ''
}

function cellClass(cell) {
  if (!cell.day) return 'empty-cell'
  const classes = ['has-day']
  if (cell.dateStr === selectedDate.value) classes.push('selected')
  if (cell.isTrading) {
    classes.push('trading-day')
    if (cell.pnl !== null) {
      if (cell.pnl > 0) classes.push('bg-positive')
      else if (cell.pnl < 0) classes.push('bg-negative')
    }
  } else {
    classes.push('non-trading')
  }
  return classes
}

function formatMoney(val) {
  if (val == null) return '-'
  const n = Number(val)
  const prefix = n > 0 ? '+' : ''
  return prefix + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatCompact(val) {
  if (val == null) return ''
  const n = Number(val)
  const prefix = n > 0 ? '+' : ''
  if (Math.abs(n) >= 10000) {
    return prefix + (n / 10000).toFixed(1) + '万'
  }
  return prefix + n.toFixed(0)
}

// Format market value compactly for calendar cells (e.g. ¥45.8万)
function formatMv(val) {
  if (val == null) return ''
  const n = Number(val)
  if (n >= 10000) return '¥' + (n / 10000).toFixed(1) + '万'
  return '¥' + n.toFixed(0)
}

function formatNum(val) {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.calendar-view {
  padding: 0;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 20px;
  color: #303133;
}

/* Summary card */
.summary-card {
  position: sticky;
  top: 20px;
}

.summary-title {
  font-weight: 600;
  font-size: 15px;
}

.summary-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  color: #909399;
  font-size: 13px;
}

.summary-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.summary-loading,
.summary-empty {
  padding: 20px 0;
  text-align: center;
  color: #909399;
}

/* Calendar card */
.calendar-card {
  min-height: 400px;
}

.month-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  gap: 8px;
}

.month-label {
  font-size: 18px;
  font-weight: 600;
  min-width: 120px;
  text-align: center;
}

/* Calendar grid */
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}

.weekday-header {
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  padding: 8px 0;
  border-bottom: 1px solid #ebeef5;
}

.day-cell {
  min-height: 76px;
  padding: 6px;
  border-radius: 6px;
  cursor: default;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.day-cell.has-day {
  cursor: pointer;
}

.day-cell.has-day:hover {
  border-color: #409eff;
}

.day-cell.empty-cell {
  background: transparent;
}

.day-cell.non-trading {
  background: #fafafa;
}

.day-cell.trading-day {
  background: #f5f7fa;
}

.day-cell.bg-positive {
  background: #f0f9eb;
}

.day-cell.bg-negative {
  background: #fef0f0;
}

.day-cell.selected {
  border-color: #409eff;
  box-shadow: 0 0 0 1px #409eff;
}

.day-number {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 2px;
}

.day-mv {
  font-size: 11px;
  color: #909399;
  margin-bottom: 1px;
}

.day-pnl {
  font-size: 12px;
  font-weight: 600;
}

/* PnL colors */
.pnl-positive {
  color: #f56c6c;
}

.pnl-negative {
  color: #67c23a;
}

/* Detail card */
.detail-card {
  margin-top: 16px;
}
</style>
