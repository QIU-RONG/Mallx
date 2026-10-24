<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { addressList, cartList, couponMy, orderCreate, payBatch } from '../api'
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
    const ids = j.data || []
    cartStore.clear()
    if (ids.length > 1) {
      // Day 78：拆单后一次付清，避免用户逐张点「支付」
      await payBatch(ids)
      ElMessage.success(`购物车含多家店铺，已拆分为 ${ids.length} 个订单并完成支付`)
      router.push('/account/orders')
    } else {
      ElMessage.success('下单成功')
      router.push(`/orders/${ids[0]}`)
    }
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
      <div v-else class="addrs">
        <button
          v-for="a in addresses"
          :key="a.id"
          type="button"
          class="addr"
          :class="{ sel: addressId === a.id }"
          @click="addressId = a.id"
        >
          <span class="dot" :class="{ on: addressId === a.id }" />
          <span class="addr-main">
            <span class="addr-top">
              <span class="who">{{ a.receiverName }}</span>
              <span class="phone">{{ a.receiverPhone }}</span>
              <span v-if="a.isDefault" class="badge">默认</span>
            </span>
            <span class="where">{{ a.province }} {{ a.city }} {{ a.district }} {{ a.detailAddress }}</span>
          </span>
          <svg
            v-if="addressId === a.id"
            class="tick"
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="m5 12 5 5L19 7" />
          </svg>
        </button>
      </div>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>优惠券</template>
      <div class="coupons">
        <button
          type="button"
          class="coupon"
          :class="{ sel: couponId == null }"
          @click="couponId = null"
        >
          <span class="dot" :class="{ on: couponId == null }" />
          <span class="coupon-name">不使用优惠券</span>
        </button>
        <button
          v-for="c in usableCoupons"
          :key="c.id"
          type="button"
          class="coupon"
          :class="{ sel: couponId === c.id }"
          @click="couponId = c.id"
        >
          <span class="dot" :class="{ on: couponId === c.id }" />
          <span class="coupon-main">
            <span class="coupon-name">{{ c.couponName }}</span>
            <span class="coupon-cond">
              <template v-if="c.discountAmount">满 {{ c.minAmount }} 减 {{ c.discountAmount }}</template>
              <template v-else-if="c.discountRate">{{ c.discountRate }} 折，满 {{ c.minAmount }}</template>
            </span>
          </span>
        </button>
      </div>
      <p v-if="usableCoupons.length === 0" class="hint">暂无可用券 —— 去「我的优惠券」领一张再回来</p>
    </el-card>

    <el-card shadow="never">
      <div class="summary">
        <span>共 {{ quantity }} 件</span>
        <span class="amount">应付 ¥{{ amount }}</span>
        <el-button type="primary" size="large" :loading="submitting" @click="submit">
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
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s var(--mx-ease),
    background 0.18s var(--mx-ease);
}
.addr:hover {
  border-color: var(--mx-ink-3);
}
.addr.sel {
  border-color: var(--mx-ink);
  background: var(--mx-line-soft);
}
.dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1px solid var(--mx-ink-3);
  flex: none;
  position: relative;
}
.dot.on {
  border-color: var(--mx-accent);
}
.dot.on::after {
  content: '';
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  background: var(--mx-accent);
}
.addr-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.addr-top {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.who {
  font-weight: 600;
  color: var(--mx-ink);
}
.phone {
  font-size: 12px;
  color: var(--mx-ink-2);
  font-family: Georgia, 'Times New Roman', serif;
}
.badge {
  font-size: 11px;
  color: var(--mx-accent);
  border: 1px solid var(--mx-accent);
  border-radius: 999px;
  padding: 0 7px;
}
.where {
  font-size: 13px;
  color: var(--mx-ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tick {
  flex: none;
  color: var(--mx-accent);
}
.addrs {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 360px;
  overflow: auto;
  padding-right: 4px;
}
.coupons {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.coupon {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 16px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s var(--mx-ease);
}
.coupon:hover {
  border-color: var(--mx-ink-3);
}
.coupon.sel {
  border-color: var(--mx-ink);
  background: var(--mx-line-soft);
}
.coupon-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.coupon-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--mx-ink);
}
.coupon-cond {
  font-size: 12px;
  color: var(--mx-ink-3);
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
