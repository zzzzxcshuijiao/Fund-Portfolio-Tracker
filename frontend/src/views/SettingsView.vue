<template>
  <div class="settings-view">
    <h2 class="page-title">设置</h2>

    <!-- Manual Refresh -->
    <el-card shadow="hover" class="settings-card">
      <template #header>
        <span>净值管理</span>
      </template>

      <div class="manual-section">
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="refreshing"
          @click="handleRefreshNav"
          size="large"
        >
          立即刷新全部净值
        </el-button>
        <span class="status-text" v-if="!refreshing">
          约需 1-2 分钟（158只基金）
        </span>
      </div>

      <div class="manual-section">
        <el-button
          type="success"
          :loading="snapshotting"
          @click="handleCreateSnapshot"
          size="large"
        >
          生成今日快照
        </el-button>
        <span class="status-text">记录当前资产总值，建议刷新净值后执行</span>
      </div>

      <el-alert
        v-if="snapshotResult"
        :title="`快照已生成：${snapshotResult.snapshot_date}，总资产 ￥${Number(snapshotResult.total_market_value).toLocaleString('zh-CN', {minimumFractionDigits: 2})}`"
        type="success"
        show-icon
        closable
        style="margin-top: 16px"
      />

      <!-- Refresh Result -->
      <el-alert
        v-if="refreshResult"
        :title="`刷新完成：${refreshResult.updated} 只成功，${refreshResult.failed} 只失败`"
        :type="refreshResult.failed === 0 ? 'success' : 'warning'"
        show-icon
        closable
        style="margin-top: 16px"
      />

      <!-- Status Display -->
      <div class="status-section">
        <el-descriptions :column="2" border size="small" title="数据状态">
          <el-descriptions-item label="最新净值日期">
            {{ navStatus.latest_nav_date ?? '--' }}
          </el-descriptions-item>
          <el-descriptions-item label="持仓基金总数">
            {{ navStatus.total_funds ?? 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="已有净值">
            {{ navStatus.funds_with_nav ?? 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="缺失净值">
            <el-tag :type="(navStatus.funds_missing_nav ?? 0) > 0 ? 'danger' : 'success'" size="small">
              {{ navStatus.funds_missing_nav ?? 0 }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <!-- Data Maintenance -->
    <el-card shadow="hover" class="settings-card">
      <template #header>
        <span>数据维护</span>
      </template>

      <el-alert type="info" :closable="false" style="margin-bottom: 16px">
        <template #title>初次使用建议按顺序执行：① 回填历史净值 → ② 从导入记录回填历史快照</template>
      </el-alert>

      <div class="manual-section">
        <el-button
          type="primary"
          plain
          :loading="navHistoryBackfilling"
          @click="handleBackfillNavHistory"
          size="large"
        >
          ① 回填历史净值数据
        </el-button>
        <span class="status-text">从东方财富拉取自首次导入以来的全量历史净值（约需 1-3 分钟）</span>
      </div>
      <el-alert
        v-if="navHistoryResult"
        :title="`历史净值回填完成：${navHistoryResult.funds} 只基金，共 ${navHistoryResult.nav_records} 条记录，起始日期 ${navHistoryResult.start_date}`"
        type="success"
        show-icon
        closable
        style="margin-top: 8px; margin-bottom: 8px"
      />

      <div class="manual-section">
        <el-button
          type="danger"
          plain
          :loading="historicalBackfilling"
          @click="handleHistoricalBackfill"
          size="large"
        >
          ② 从导入记录回填历史快照
        </el-button>
        <span class="status-text">为每次导入日期创建快照，市值来自导入的持仓数据</span>
      </div>
      <el-alert
        v-if="historicalBackfillResult"
        :title="`历史快照回填完成，新增 ${historicalBackfillResult.created} 条记录`"
        type="success"
        show-icon
        closable
        style="margin-top: 8px; margin-bottom: 8px"
      />

      <div class="manual-section">
        <el-button
          type="warning"
          :loading="backfilling"
          @click="handleBackfillNav"
          size="large"
        >
          重算组合净值
        </el-button>
        <span class="status-text">重新计算所有历史快照的组合净值（回填快照后执行）</span>
      </div>
      <el-alert
        v-if="backfillDone"
        title="回填完成，请刷新仪表盘查看组合净值走势"
        type="success"
        show-icon
        closable
        style="margin-top: 16px"
      />
    </el-card>

    <!-- Schedule Info -->
    <el-card shadow="hover" class="settings-card">
      <template #header>
        <span>自动调度</span>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="净值更新">
          工作日 20:00 自动抓取
        </el-descriptions-item>
        <el-descriptions-item label="净值补漏">
          工作日 22:00 补抓晚公布基金
        </el-descriptions-item>
        <el-descriptions-item label="每日快照">
          工作日 22:30 生成组合快照
        </el-descriptions-item>
        <el-descriptions-item label="启动补漏">
          应用启动时自动检查并补抓遗漏数据
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { refreshNav, getNavStatus, backfillPortfolioNav, createSnapshot, backfillSnapshots, backfillNavHistory } from '../api/index.js'

const refreshing = ref(false)
const refreshResult = ref(null)
const navStatus = ref({})
const backfilling = ref(false)
const backfillDone = ref(false)
const snapshotting = ref(false)
const snapshotResult = ref(null)
const historicalBackfilling = ref(false)
const historicalBackfillResult = ref(null)
const navHistoryBackfilling = ref(false)
const navHistoryResult = ref(null)

async function handleRefreshNav() {
  refreshing.value = true
  refreshResult.value = null
  try {
    refreshResult.value = await refreshNav()
    ElMessage.success(`净值刷新完成：${refreshResult.value.updated} 只成功`)
    loadStatus()
  } catch {
    // Errors handled by interceptor
  } finally {
    refreshing.value = false
  }
}

async function loadStatus() {
  try {
    navStatus.value = await getNavStatus()
  } catch {
    // Errors handled by interceptor
  }
}

async function handleBackfillNav() {
  backfilling.value = true
  backfillDone.value = false
  try {
    await backfillPortfolioNav()
    backfillDone.value = true
    ElMessage.success('组合净值回填完成')
  } catch {
    // Errors handled by interceptor
  } finally {
    backfilling.value = false
  }
}

async function handleCreateSnapshot() {
  snapshotting.value = true
  snapshotResult.value = null
  try {
    snapshotResult.value = await createSnapshot()
    ElMessage.success(`快照已生成：${snapshotResult.value.snapshot_date}`)
  } catch {
    // Errors handled by interceptor
  } finally {
    snapshotting.value = false
  }
}

async function handleBackfillNavHistory() {
  navHistoryBackfilling.value = true
  navHistoryResult.value = null
  try {
    navHistoryResult.value = await backfillNavHistory()
    ElMessage.success(`历史净值回填完成：${navHistoryResult.value.nav_records} 条记录`)
    loadStatus()
  } catch {
    // Errors handled by interceptor
  } finally {
    navHistoryBackfilling.value = false
  }
}

async function handleHistoricalBackfill() {
  historicalBackfilling.value = true
  historicalBackfillResult.value = null
  try {
    historicalBackfillResult.value = await backfillSnapshots()
    ElMessage.success(`历史快照回填完成，新增 ${historicalBackfillResult.value.created} 条`)
  } catch {
    // Errors handled by interceptor
  } finally {
    historicalBackfilling.value = false
  }
}

onMounted(() => {
  loadStatus()
})
</script>

<style scoped>
.settings-view {
  padding: 4px;
}

.page-title {
  margin: 0 0 20px 0;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.settings-card {
  margin-bottom: 20px;
  max-width: 800px;
}

.manual-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.status-text {
  color: #909399;
  font-size: 13px;
}

.status-section {
  margin-top: 20px;
}
</style>
