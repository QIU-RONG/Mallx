<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { couponAvailable, couponMy, couponReceive } from '../api'
import type { CouponVO, UserCouponVO } from '../types/api'

const available = ref<CouponVO[]>([])
const mine = ref<UserCouponVO[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const [a, m] = await Promise.all([
      couponAvailable({ page: 1, size: 50 }),
      couponMy({ page: 1, size: 100 }),
    ])
    available.value = a.data?.records || []
    mine.value = m.data?.records || []
  } finally {
    loading.value = false
  }
}

async function receive(c: CouponVO) {
  await couponReceive(c.id)
  ElMessage.success('领取成功')
  load()
}

function face(c: CouponVO) {
  if (c.discountAmount) return `满 ${c.minAmount} 减 ${c.discountAmount}`
  if (c.discountRate) return `${c.discountRate} 折（满 ${c.minAmount}）`
  return '优惠券'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="wrap">
    <h3>我的优惠券</h3>
    <el-empty v-if="!loading && mine.length === 0" description="还没有券 —— 从下面的「可领取」里领一张" />
    <div v-else class="grid">
      <el-card v-for="c in mine" :key="c.id" shadow="hover" class="cp" :class="{ dim: c.expired || c.status !== 'UNUSED' }">
        <div class="name">{{ c.couponName }}</div>
        <div class="face">
          <template v-if="c.discountAmount">￥{{ c.discountAmount }}</template>
          <template v-else-if="c.discountRate">{{ c.discountRate }} 折</template>
        </div>
        <div class="hint">满 {{ c.minAmount }} 可用</div>
        <div class="hint">有效期至 {{ c.endTime || '-' }}</div>
        <el-tag
          size="small"
          :type="c.expired ? 'info' : c.status === 'USED' ? 'success' : 'warning'"
        >
          {{ c.expired ? '已过期' : c.status === 'USED' ? '已使用' : '未使用' }}
        </el-tag>
      </el-card>
    </div>

    <h3 class="sec">可领取</h3>
    <el-empty v-if="!loading && available.length === 0" description="暂无可领取的券" />
    <div v-else class="grid">
      <el-card v-for="c in available" :key="c.id" shadow="hover" class="cp">
        <div class="name">{{ c.name }}</div>
        <div class="face">
          <template v-if="c.discountAmount">￥{{ c.discountAmount }}</template>
          <template v-else-if="c.discountRate">{{ c.discountRate }} 折</template>
        </div>
        <div class="hint">{{ face(c) }}</div>
        <div class="hint">
          剩余 {{ (c.totalCount ?? 0) - (c.receivedCount ?? 0) }} / {{ c.totalCount ?? 0 }}
        </div>
        <el-button type="danger" size="small" style="width: 100%" @click="receive(c)">
          立即领取
        </el-button>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
  min-height: 260px;
}
.sec {
  margin-top: 24px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.cp.dim {
  opacity: 0.55;
}
.name {
  font-weight: 600;
}
.face {
  color: #f56c6c;
  font-size: 22px;
  font-weight: 700;
  margin: 6px 0;
}
.hint {
  color: #909399;
  font-size: 12px;
}
</style>
