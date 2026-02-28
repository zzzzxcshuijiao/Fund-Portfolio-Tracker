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
import { refreshNav, getNavStatus } from '../api/index.js'

const refreshing = ref(false)
const refreshResult = ref(null)
const navStatus = ref({})

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
