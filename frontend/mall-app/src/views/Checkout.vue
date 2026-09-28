<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { addressList, cartList, couponMy, orderCreate } from '../api'
import type { AddressVO, UserCouponVO } from '../types/api'
import { useCartStore } from '../stores/cart'

const router = useRouter()
const cartStore = useCartStore()

const amount = ref(0)
const quantity = ref(0)
const addresses = ref<AddressVO[]>([])
const addressId = ref<number | null>(null)
const coupons = ref<UserCouponVO[]>([])
const couponId = ref<number | null>(null)
const submitting = ref(false)
const loading = ref(false)

/** 可用券 = 未使用且未过期（过期由后端 SQL 算出来，前端只展示） */
const usableCoupons = computed(() =>
  coupons.value.filter((c) => c.status === 'UNUSED' && !c.expired),
)

onMounted(async () => {
  loading.value = true
  try {
    const [cart, addr, cp] = await Promise.all([
      cartList(),
      addressList(),
      couponMy({ page: 1, size: 100 }),
    ])
    amount.value = Number(cart.data.selectedAmount || 0)
    quantity.value = cart.data.selectedQuantity || 0
    addresses.value = addr.data || []
    coupons.value = (cp.data?.records || []).filter((c) => c.status === 'UNUSED' && !c.expired)
    const def = addresses.value.find((a) => a.isDefault) || addresses.value[0]
    addressId.value = def?.id ?? null
  } finally {
    loading.value = false
  }
})

async function submit() {
  if (addressId.value == null) {
    ElMessage.warning('请选择收货地址')
    return
  }
  submitting.value = true
  try {
    const j = await orderCreate(addressId.value, couponId.value)
    ElMessage.success('下单成功')
    cartStore.clear()
    router.push(`/orders/${j.data}`)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div v-loading="loading" class="wrap">
    <h3>确认订单</h3>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>收货地址</template>
      <el-empty v-if="addresses.length === 0" description="还没有收货地址（种子账号 demo 自带一条）" />
      <el-radio-group v-else v-model="addressId" class="addr-group">
        <el-radio v-for="a in addresses" :key="a.id" :value="a.id" class="addr">
          <span class="who">{{ a.receiverName }} {{ a.receiverPhone }}</span>
          <span class="where">{{ a.province }}{{ a.city }}{{ a.district }} {{ a.detailAddress }}</span>
          <el-tag v-if="a.isDefault" size="small" type="success">默认</el-tag>
        </el-radio>
      </el-radio-group>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>优惠券</template>
      <el-radio-group v-model="couponId" class="coupon-group">
        <el-radio :value="null">不使用优惠券</el-radio>
        <el-radio
          v-for="c in usableCoupons"
          :key="c.id"
          :value="c.id"
          class="coupon"
        >
          {{ c.couponName }}
          <span class="hint">
            （<template v-if="c.discountAmount">满 {{ c.minAmount }} 减 {{ c.discountAmount }}</template>
            <template v-else-if="c.discountRate">{{ c.discountRate }} 折，满 {{ c.minAmount }}</template>）
          </span>
        </el-radio>
      </el-radio-group>
      <p v-if="usableCoupons.length === 0" class="hint">暂无可用券 —— 去「我的优惠券」领一张再回来</p>
    </el-card>

    <el-card shadow="never">
      <div class="summary">
        <span>共 {{ quantity }} 件</span>
        <span class="amount">应付 ￥{{ amount }}</span>
        <el-button type="danger" size="large" :loading="submitting" @click="submit">
          提交订单
        </el-button>
      </div>
      <p class="hint">★ 提交后订单进入「待支付」—— 超时 2 分钟会自动关单（后端扫描 + MQ 双保险）。</p>
    </el-card>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 900px;
  margin: 0 auto;
  padding: 16px;
  min-height: 260px;
}
.addr-group,
.coupon-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.addr {
  display: flex;
  align-items: center;
  gap: 10px;
}
.who {
  font-weight: 600;
}
.where {
  color: #606266;
}
.summary {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-content: flex-end;
}
.amount {
  color: #f56c6c;
  font-size: 22px;
  font-weight: 700;
}
.hint {
  color: #909399;
  font-size: 12px;
  margin-top: 8px;
}
</style>
