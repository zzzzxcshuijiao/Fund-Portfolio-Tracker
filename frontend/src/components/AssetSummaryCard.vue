<template>
  <el-card shadow="hover" class="summary-card" :body-style="{ padding: '20px' }">
    <div class="card-inner">
      <div class="card-icon" :style="{ backgroundColor: color + '20', color: color }">
        <el-icon :size="28">
          <component :is="icon" />
        </el-icon>
      </div>
      <div class="card-content">
        <div class="card-title">{{ title }}</div>
        <div class="card-value" :style="{ color: valueColor }">
          {{ prefix }}{{ formattedValue }}<span v-if="suffix" class="card-suffix">{{ suffix }}</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, default: '--' },
  value: { type: [Number, String], default: 0 },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' },
  color: { type: String, default: '#409eff' },
  icon: { type: String, default: 'Wallet' },
})

const formattedValue = computed(() => {
  if (props.value == null) return '--'
  const num = Number(props.value)
  if (isNaN(num)) return props.value
  if (props.prefix === '￥') {
    return num.toLocaleString('zh-CN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  }
  return num.toLocaleString('zh-CN')
})

const valueColor = computed(() => {
  const num = Number(props.value)
  if (props.prefix === '￥' && num < 0) return '#67c23a'
  if (props.prefix === '￥' && num > 0) return props.title === '总资产' ? '#303133' : '#f56c6c'
  return '#303133'
})
</script>

<style scoped>
.summary-card {
  height: 100%;
}

.card-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}

.card-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.card-content {
  flex: 1;
  min-width: 0;
}

.card-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.card-value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-suffix {
  font-size: 14px;
  font-weight: 400;
  color: #909399;
  margin-left: 4px;
}
</style>
