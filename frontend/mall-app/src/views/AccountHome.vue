<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { couponMy, myRefunds, orderList } from '../api'
import type { OrderStatus, OrderVO } from '../types/api'
import { useAuthStore } from '../stores/auth'

/**
 * 个人中心 · 概览（Day 58）。
 *
 * <p>★★ 这里的四个数字都来自<b>真实分页接口的 total</b>，不是本地遍历：
 * 订单可能成千上万，前端为了一个角标把全部数据拉下来，是典型的「首页很重」。
 * `size: 1` 只取 total，接口本来就返回它。
 */
const router = useRouter()
const auth = useAuthStore()

const pendingPay = ref(0)
const pendingShip = ref(0)
const refunds = ref(0)
const coupons = ref(0)
const recent = ref<OrderVO[]>([])
const loading = ref(false)

const greeting = computed(() => {
  const h = new Date().getHours()
  const word = h < 6 ? '夜深了' : h < 12 ? '早上好' : h < 18 ? '下午好' : '晚上好'
  return `${word}，${auth.nickname || auth.username}`
})

const STATUS_LABEL: Record<OrderStatus, string> = {
  PENDING_PAYMENT: '待支付',
  PAID: '已支付',
  SHIPPED: '已发货',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
}

async function load() {
  loading.value = true
  try {
    const [pay, ship, refund, coupon, list] = await Promise.all([
      orderList({ page: 1, size: 1, status: 'PENDING_PAYMENT' }),
      orderList({ page: 1, size: 1, status: 'SHIPPED' }),
      myRefunds({ page: 1, size: 1 }),
      couponMy({ page: 1, size: 1 }),
      orderList({ page: 1, size: 3 }),
    ])
    pendingPay.value = pay.data.total
    pendingShip.value = ship.data.total
    refunds.value = refund.data.total
    coupons.value = coupon.data.total
    recent.value = list.data.records || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="home">
    <header class="head">
      <h1 class="title">{{ greeting }}</h1>
      <p class="sub">在这里查看订单、售后、优惠券与收货地址</p>
    </header>

    <div class="stats">
      <button class="stat" type="button" @click="router.push('/account/orders')">
        <span class="num mx-serif">{{ pendingPay }}</span>
        <span class="label">待付款</span>
      </button>
      <button class="stat" type="button" @click="router.push('/account/orders')">
        <span class="num mx-serif">{{ pendingShip }}</span>
        <span class="label">待收货</span>
      </button>
      <button class="stat" type="button" @click="router.push('/account/refunds')">
        <span class="num mx-serif">{{ refunds }}</span>
        <span class="label">售后记录</span>
      </button>
      <button class="stat" type="button" @click="router.push('/account/coupons')">
        <span class="num mx-serif">{{ coupons }}</span>
        <span class="label">我的优惠券</span>
      </button>
    </div>

    <section class="recent">
      <div class="section-head">
        <h2 class="section-title">最近订单</h2>
        <router-link class="more" to="/account/orders">全部订单 →</router-link>
      </div>

      <el-empty v-if="!recent.length" description="还没有订单，去逛逛吧">
        <el-button type="primary" @click="router.push('/')">去商城</el-button>
      </el-empty>

      <ul v-else class="order-list">
        <li v-for="o in recent" :key="o.id" class="order" @click="router.push(`/orders/${o.id}`)">
          <div class="order-main">
            <div class="order-no">{{ o.orderNo }}</div>
            <div class="order-time">{{ o.createdAt?.replace('T', ' ').slice(0, 16) }}</div>
          </div>
          <div class="order-side">
            <span class="status">{{ STATUS_LABEL[o.status] }}</span>
            <span class="amount mx-serif">¥{{ Number(o.payAmount).toFixed(2) }}</span>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.home {
  min-height: 320px;
}
.head {
  padding-bottom: 24px;
  border-bottom: 1px solid var(--mx-line);
}
.title {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--mx-ink);
}
.sub {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--mx-ink-2);
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 28px;
}
.stat {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 22px 20px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.18s var(--mx-ease),
    transform 0.18s var(--mx-ease);
}
.stat:hover {
  border-color: var(--mx-ink-3);
  transform: translateY(-2px);
}
.num {
  font-size: 34px;
  line-height: 1;
  color: var(--mx-ink);
}
.label {
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--mx-ink-3);
}

.recent {
  margin-top: 40px;
}
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 14px;
}
.section-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mx-ink);
}
.more {
  font-size: 12px;
  color: var(--mx-ink-3);
  text-decoration: none;
}
.more:hover {
  color: var(--mx-ink);
}

.order-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--mx-line);
}
.order {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 4px;
  border-bottom: 1px solid var(--mx-line-soft);
  cursor: pointer;
}
.order:hover {
  background: var(--mx-line-soft);
}
.order-no {
  font-size: 14px;
  color: var(--mx-ink);
  font-variant-numeric: tabular-nums;
}
.order-time {
  margin-top: 4px;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.order-side {
  display: flex;
  align-items: baseline;
  gap: 18px;
  flex: none;
}
.status {
  font-size: 12px;
  color: var(--mx-ink-2);
}
.amount {
  font-size: 16px;
  color: var(--mx-ink);
}

@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .title {
    font-size: 22px;
  }
}
</style>
