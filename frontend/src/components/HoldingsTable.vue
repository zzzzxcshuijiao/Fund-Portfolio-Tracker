<template>
  <div class="holdings-table-wrapper">
    <el-table :data="data" stripe style="width: 100%">
      <el-table-column prop="fundCode" label="基金代码" width="120" />
      <el-table-column prop="fundName" label="基金名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="platform" label="平台" width="120" />
      <el-table-column prop="shares" label="持有份额" width="130" align="right">
        <template #default="{ row }">
          {{ formatNum(row.shares) }}
        </template>
      </el-table-column>
      <el-table-column prop="nav" label="最新净值" width="110" align="right">
        <template #default="{ row }">
          {{ row.nav?.toFixed(4) ?? '--' }}
        </template>
      </el-table-column>
      <el-table-column prop="marketValue" label="市值" width="130" align="right">
        <template #default="{ row }">
          ￥{{ formatNum(row.marketValue) }}
        </template>
      </el-table-column>
      <el-table-column prop="dailyChangeRate" label="日涨跌幅" width="110" align="right">
        <template #default="{ row }">
          <span :class="pnlClass(row.dailyChangeRate)">
            {{ row.dailyChangeRate != null ? (row.dailyChangeRate * 100).toFixed(2) + '%' : '--' }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
defineProps({
  data: { type: Array, default: () => [] },
  showPagination: { type: Boolean, default: true },
})

function formatNum(val) {
  if (val == null) return '--'
  return Number(val).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function pnlClass(rate) {
  if (rate == null) return ''
  return rate > 0 ? 'text-profit' : rate < 0 ? 'text-loss' : ''
}
</script>

<style scoped>
.holdings-table-wrapper {
  width: 100%;
}

.text-profit {
  color: #f56c6c;
}

.text-loss {
  color: #67c23a;
}
</style>
