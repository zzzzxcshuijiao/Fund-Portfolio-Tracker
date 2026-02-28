<template>
  <div class="fund-detail-view">
    <!-- Back button -->
    <el-page-header @back="goBack" class="page-header">
      <template #content>
        <span class="page-header-title">
          {{ fundDetail.fund_name ?? '基金详情' }}
          <el-tag v-if="fundDetail.fund_code" size="small" type="info" class="code-tag">
            {{ fundDetail.fund_code }}
          </el-tag>
        </span>
      </template>
    </el-page-header>

    <!-- Fund Info -->
    <el-card shadow="hover" class="info-card" v-loading="loading">
      <el-descriptions :column="3" border>
        <el-descriptions-item label="基金代码">{{ fundDetail.fund_code ?? '--' }}</el-descriptions-item>
        <el-descriptions-item label="基金名称">{{ fundDetail.fund_name ?? '--' }}</el-descriptions-item>
        <el-descriptions-item label="管理公司">{{ fundDetail.management_company ?? '--' }}</el-descriptions-item>
        <el-descriptions-item label="最新净值">
          {{ fundDetail.latest_nav ? Number(fundDetail.latest_nav).toFixed(4) : '--' }}
        </el-descriptions-item>
        <el-descriptions-item label="净值日期">{{ fundDetail.latest_nav_date ?? '--' }}</el-descriptions-item>
        <el-descriptions-item label="日涨跌幅">
          <span :class="pnlClass(fundDetail.nav_change_pct)">
            {{ fundDetail.nav_change_pct != null ? Number(fundDetail.nav_change_pct).toFixed(2) + '%' : '--' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="总份额">
          {{ fundDetail.total_shares ? formatNum(fundDetail.total_shares) : '--' }}
        </el-descriptions-item>
        <el-descriptions-item label="总市值">
          ￥{{ fundDetail.total_market_value ? formatNum(fundDetail.total_market_value) : '--' }}
        </el-descriptions-item>
        <el-descriptions-item label="持仓平台数">{{ fundDetail.platform_count ?? '--' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- Holdings on different platforms -->
    <el-card shadow="hover" class="holdings-card">
      <template #header>
        <span>各平台持仓明细</span>
      </template>
      <el-table :data="platformHoldings" stripe style="width: 100%" v-loading="holdingsLoading">
        <el-table-column prop="platform" label="平台" min-width="160" show-overflow-tooltip />
        <el-table-column label="持有份额" width="140" align="right">
          <template #default="{ row }">
            {{ formatNum(row.shares) }}
          </template>
        </el-table-column>
        <el-table-column label="市值" width="140" align="right">
          <template #default="{ row }">
            ￥{{ formatNum(row.current_market_value || row.market_value) }}
          </template>
        </el-table-column>
        <el-table-column prop="fund_account" label="基金账户" width="160" show-overflow-tooltip />
        <el-table-column prop="dividend_mode" label="分红方式" width="120" />
      </el-table>
    </el-card>

    <!-- NAV History Chart -->
    <el-card shadow="hover" class="chart-card">
      <template #header>
        <div class="chart-header">
          <span>历史净值走势</span>
          <el-radio-group v-model="navDays" size="small" @change="loadNavHistory">
            <el-radio-button :value="30">近1月</el-radio-button>
            <el-radio-button :value="90">近3月</el-radio-button>
            <el-radio-button :value="180">近6月</el-radio-button>
            <el-radio-button :value="365">近1年</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <NavHistoryChart :data="navHistory" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getFundDetail, getFundNavHistory, getHoldings } from '../api/index.js'
import NavHistoryChart from '../components/NavHistoryChart.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const holdingsLoading = ref(false)
const fundDetail = ref({})
const platformHoldings = ref([])
const navHistory = ref([])
const navDays = ref(90)

function goBack() {
  router.push('/holdings')
}

function formatNum(val) {
  if (val == null) return '--'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pnlClass(val) {
  if (val == null) return ''
  return Number(val) > 0 ? 'text-profit' : Number(val) < 0 ? 'text-loss' : ''
}

async function loadDetail() {
  loading.value = true
  try {
    const code = route.params.code
    fundDetail.value = await getFundDetail(code)
  } catch {
    // Errors handled by interceptor
  } finally {
    loading.value = false
  }
}

async function loadPlatformHoldings() {
  holdingsLoading.value = true
  try {
    const code = route.params.code
    const all = await getHoldings({ search: code })
    platformHoldings.value = all.filter(h => h.fund_code === code)
  } catch {
    // ignore
  } finally {
    holdingsLoading.value = false
  }
}

async function loadNavHistory() {
  try {
    const code = route.params.code
    navHistory.value = await getFundNavHistory(code, { days: navDays.value })
  } catch {
    // Errors handled by interceptor
  }
}

onMounted(() => {
  loadDetail()
  loadPlatformHoldings()
  loadNavHistory()
})
</script>

<style scoped>
.fund-detail-view {
  padding: 4px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header-title {
  font-size: 18px;
  font-weight: 600;
}

.code-tag {
  margin-left: 8px;
}

.info-card {
  margin-bottom: 20px;
}

.holdings-card {
  margin-bottom: 20px;
}

.chart-card {
  margin-bottom: 20px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
