<template>
  <div class="dashboard-view">
    <h2 class="page-title">投资概览</h2>

    <!-- Summary Cards -->
    <el-row :gutter="20" class="summary-row">
      <el-col :span="6">
        <AssetSummaryCard
          title="总资产"
          :value="summary.total_market_value"
          prefix="￥"
          color="#409eff"
          icon="Wallet"
        />
      </el-col>
      <el-col :span="6">
        <AssetSummaryCard
          title="持有基金"
          :value="summary.total_funds"
          :suffix="`只 / ${summary.total_holdings}笔`"
          color="#67c23a"
          icon="Coin"
        />
      </el-col>
      <el-col :span="6">
        <AssetSummaryCard
          title="日涨跌"
          :value="summary.daily_pnl"
          prefix="￥"
          color="#e6a23c"
          icon="DataLine"
        />
      </el-col>
      <el-col :span="6">
        <AssetSummaryCard
          title="覆盖平台"
          :value="summary.total_platforms"
          suffix="个"
          color="#909399"
          icon="OfficeBuilding"
        />
      </el-col>
    </el-row>

    <!-- Charts Row -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>平台资产分布</span>
          </template>
          <PlatformPieChart :data="platformData" />
          <el-table :data="platformData" stripe size="small" style="margin-top: 12px">
            <el-table-column prop="platform" label="平台" min-width="120" show-overflow-tooltip />
            <el-table-column label="市值" width="140" align="right">
              <template #default="{ row }">
                ￥{{ formatNum(row.market_value) }}
              </template>
            </el-table-column>
            <el-table-column label="日涨跌额" width="130" align="right">
              <template #default="{ row }">
                <span :class="pnlClass(row.daily_pnl)">
                  {{ row.daily_pnl != null ? formatNum(row.daily_pnl) : '--' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="占比" width="90" align="right">
              <template #default="{ row }">
                {{ row.percentage != null ? Number(row.percentage).toFixed(2) + '%' : '--' }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <span>组合净值走势</span>
          </template>
          <PortfolioNavChart :data="dailyPnlData" />
        </el-card>
      </el-col>
    </el-row>

    <!-- Top Holdings -->
    <el-card shadow="hover" class="top-holdings-card">
      <template #header>
        <span>重仓基金 TOP 10</span>
      </template>
      <el-table :data="topHoldings" stripe style="width: 100%">
        <el-table-column prop="fund_code" label="基金代码" width="120" />
        <el-table-column prop="fund_name" label="基金名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="最新净值" width="120" align="right">
          <template #default="{ row }">
            {{ row.latest_nav ? Number(row.latest_nav).toFixed(4) : '--' }}
          </template>
        </el-table-column>
        <el-table-column label="总份额" width="140" align="right">
          <template #default="{ row }">
            {{ formatNum(row.total_shares) }}
          </template>
        </el-table-column>
        <el-table-column label="总市值" width="140" align="right" sortable>
          <template #default="{ row }">
            ￥{{ formatNum(row.total_market_value) }}
          </template>
        </el-table-column>
        <el-table-column label="日涨跌" width="110" align="right">
          <template #default="{ row }">
            <span :class="pnlClass(row.nav_change_pct)">
              {{ row.nav_change_pct != null ? Number(row.nav_change_pct).toFixed(2) + '%' : '--' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="平台数" width="80" align="center">
          <template #default="{ row }">
            {{ row.platform_count }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  getSummary,
  getPlatformDistribution,
  getDailyPnl,
  getTopHoldings,
} from '../api/index.js'
import AssetSummaryCard from '../components/AssetSummaryCard.vue'
import PlatformPieChart from '../components/PlatformPieChart.vue'
import PortfolioNavChart from '../components/PortfolioNavChart.vue'

const summary = ref({
  total_market_value: 0,
  daily_pnl: null,
  daily_pnl_pct: null,
  total_holdings: 0,
  total_funds: 0,
  total_platforms: 0,
})
const platformData = ref([])
const dailyPnlData = ref([])
const topHoldings = ref([])

function formatNum(val) {
  if (val == null) return '--'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pnlClass(val) {
  if (val == null) return ''
  return Number(val) > 0 ? 'text-profit' : Number(val) < 0 ? 'text-loss' : ''
}

async function loadDashboard() {
  try {
    const [summaryRes, platformRes, pnlRes, holdingsRes] = await Promise.allSettled([
      getSummary(),
      getPlatformDistribution(),
      getDailyPnl({ days: 90 }),
      getTopHoldings({ limit: 10 }),
    ])

    if (summaryRes.status === 'fulfilled') summary.value = summaryRes.value
    if (platformRes.status === 'fulfilled') platformData.value = platformRes.value
    if (pnlRes.status === 'fulfilled') dailyPnlData.value = pnlRes.value
    if (holdingsRes.status === 'fulfilled') topHoldings.value = holdingsRes.value
  } catch {
    // Errors already handled by the axios interceptor
  }
}

onMounted(() => {
  loadDashboard()
})
</script>

<style scoped>
.dashboard-view {
  padding: 4px;
}

.page-title {
  margin: 0 0 20px 0;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.summary-row {
  margin-bottom: 20px;
}

.chart-row {
  margin-bottom: 20px;
}

.top-holdings-card {
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
