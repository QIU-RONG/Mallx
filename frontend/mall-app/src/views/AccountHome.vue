<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { couponMy, myRefunds, orderDetail, orderList } from '../api'
import ProductThumb from '../components/ProductThumb.vue'
import type { OrderItemVO, OrderStatus, OrderVO } from '../types/api'
import { useAuthStore } from '../stores/auth'

/**
 * 个人中心 · 概览（Day 58 / Day 63 改版）。
 *
 * <p>★★ 改版原因（用户原话）：「应该直接看到的是商品，而不是订单编号」。
 * 订单号是给客服对账用的，顾客认的是「我买的那台手机」——
 * 所以最近订单改成【商品卡】：缩略图 + 商品名 + 状态 + 实付，订单号降为次要信息。
 *
 * <p>★ 数据成本：订单列表接口不返回明细，这里对最近 3 单各查一次详情（并发），
 * 只取第一件商品做封面。3 个请求换「一眼看懂买了什么」，值得；订单多了不要照搬。
 */
const router = useRouter()
const auth = useAuthStore()

const pendingPay = ref(0)
const pendingShip = ref(0)
const refunds = ref(0)
const coupons = ref(0)
const recent = ref<Array<{ order: OrderVO; item: OrderItemVO | null; count: number }>>([])
const loading = ref(false)

const greeting = computed(() => {
  const h = new Date().getHours()
  const word = h < 6 ? '夜深了' : h < 12 ? '早上好' : h < 18 ? '下午好' : '晚上好'
  return `${word}，${auth.nickname || auth.username}`
})

const STATUS_META: Record<OrderStatus, { label: string; type: 'info' | 'warning' | 'primary' | 'success' }> = {
  PENDING_PAYMENT: { label: '待支付', type: 'warning' },
  PAID: { label: '待发货', type: 'primary' },
  SHIPPED: { label: '待收货', type: 'primary' },
  COMPLETED: { label: '已完成', type: 'success' },
  CANCELLED: { label: '已取消', type: 'info' },
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

    const rows = list.data.records || []
    const details = await Promise.all(
      rows.map((o) => orderDetail(o.id).catch(() => null)),
    )
    recent.value = rows.map((o, i) => ({
      order: o,
      item: details[i]?.data?.items?.[0] ?? null,
      // 明细数量拿不到时退化为 1，不显示「等 0 件」这种错话
      count: details[i]?.data?.items?.length ?? 1,
    }))
  } finally {
    loading.value = false
  }
}

const quickLinks = [
  { to: '/account/orders', label: '我的订单', icon: 'box' },
  { to: '/account/refunds', label: '退款售后', icon: 'shield' },
  { to: '/account/coupons', label: '优惠券', icon: 'ticket' },
  { to: '/account/addresses', label: '收货地址', icon: 'pin' },
]

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="home">
    <header class="head">
      <h1 class="title">{{ greeting }}</h1>
      <p class="sub">这里能看到你买过的东西、在路上的包裹和售后进度</p>
    </header>

    <!-- ═══════ 四个数字（带图形） ═══════ -->
    <div class="stats">
      <button class="stat" type="button" @click="router.push('/account/orders')">
        <span class="stat-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="6" width="18" height="13" rx="2" />
            <path d="M3 10h18M7 15h4" />
          </svg>
        </span>
        <span class="num mx-serif">{{ pendingPay }}</span>
        <span class="label">待付款</span>
      </button>

      <button class="stat" type="button" @click="router.push('/account/orders')">
        <span class="stat-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 7h11v9H3zM14 10h4l3 3v3h-7" />
            <circle cx="7" cy="18" r="1.6" />
            <circle cx="17.5" cy="18" r="1.6" />
          </svg>
        </span>
        <span class="num mx-serif">{{ pendingShip }}</span>
        <span class="label">待收货</span>
      </button>

      <button class="stat" type="button" @click="router.push('/account/refunds')">
        <span class="stat-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3 4.5 6v5.5c0 4.4 3.1 7.9 7.5 9.5 4.4-1.6 7.5-5.1 7.5-9.5V6L12 3Z" />
            <path d="m9 12 2 2 4-4.5" />
          </svg>
        </span>
        <span class="num mx-serif">{{ refunds }}</span>
        <span class="label">售后记录</span>
      </button>

      <button class="stat" type="button" @click="router.push('/account/coupons')">
        <span class="stat-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 9V7a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v2a2.5 2.5 0 0 0 0 6v2a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-2a2.5 2.5 0 0 0 0-6Z" />
            <path d="M13 6v12" stroke-dasharray="2 2.4" />
          </svg>
        </span>
        <span class="num mx-serif">{{ coupons }}</span>
        <span class="label">我的优惠券</span>
      </button>
    </div>

    <!-- ═══════ 快捷入口（带图形） ═══════ -->
    <nav class="quick">
      <router-link v-for="q in quickLinks" :key="q.to" :to="q.to" class="quick-item">
        <span class="quick-icon">
          <svg v-if="q.icon === 'box'" viewBox="0 0 24 24" width="18" height="18" fill="none"
            stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
            <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" />
            <path d="M4 7.5 12 12l8-4.5M12 12v9" />
          </svg>
          <svg v-else-if="q.icon === 'shield'" viewBox="0 0 24 24" width="18" height="18" fill="none"
            stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3 4.5 6v5.5c0 4.4 3.1 7.9 7.5 9.5 4.4-1.6 7.5-5.1 7.5-9.5V6L12 3Z" />
            <path d="M12 8v4l2.5 2" />
          </svg>
          <svg v-else-if="q.icon === 'ticket'" viewBox="0 0 24 24" width="18" height="18" fill="none"
            stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">
            <path d="M3 9V7a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v2a2.5 2.5 0 0 0 0 6v2a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-2a2.5 2.5 0 0 0 0-6Z" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
            stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11Z" />
            <circle cx="12" cy="10" r="2.4" />
          </svg>
        </span>
        <span class="quick-label">{{ q.label }}</span>
      </router-link>
    </nav>

    <!-- ═══════ 最近订单：以【商品】为主体 ═══════ -->
    <section class="recent">
      <div class="section-head">
        <h2 class="section-title">最近买过</h2>
        <router-link class="more" to="/account/orders">全部订单 →</router-link>
      </div>

      <el-empty v-if="!recent.length && !loading" description="还没有订单，去逛逛吧">
        <el-button type="primary" @click="router.push('/')">去商城</el-button>
      </el-empty>

      <ul v-else class="order-list">
        <li v-for="r in recent" :key="r.order.id" class="order" @click="router.push(`/orders/${r.order.id}`)">
          <div class="order-pic">
            <ProductThumb
              :src="r.item?.image"
              :name="r.item?.productName || r.order.receiverName"
              :seed="r.order.id"
            />
          </div>
          <div class="order-main">
            <div class="order-name">{{ r.item?.productName || '订单商品' }}</div>
            <div class="order-sub">
              <span>{{ r.item?.skuName || '' }}</span>
              <span v-if="r.count > 1" class="order-count">等 {{ r.count }} 件</span>
            </div>
          </div>
          <div class="order-side">
            <el-tag :type="STATUS_META[r.order.status].type" size="small" effect="plain">
              {{ STATUS_META[r.order.status].label }}
            </el-tag>
            <span class="amount mx-serif">¥{{ Number(r.order.payAmount).toFixed(2) }}</span>
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

/* ───── 数字卡 ───── */
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 28px;
}
.stat {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 10px;
  row-gap: 6px;
  align-items: center;
  padding: 20px;
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
.stat-icon {
  grid-row: 1 / span 2;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--mx-line-soft);
  color: var(--mx-ink-2);
  display: flex;
  align-items: center;
  justify-content: center;
}
.num {
  font-size: 30px;
  line-height: 1;
  color: var(--mx-ink);
}
.label {
  font-size: 12px;
  letter-spacing: 0.06em;
  color: var(--mx-ink-3);
}

/* ───── 快捷入口 ───── */
.quick {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.quick-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  color: var(--mx-ink);
  text-decoration: none;
  font-size: 13px;
  transition: border-color 0.18s var(--mx-ease);
}
.quick-item:hover {
  border-color: var(--mx-ink-3);
}
.quick-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--mx-line-soft);
  color: var(--mx-ink-2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

/* ───── 最近订单（商品为主） ───── */
.recent {
  margin-top: 40px;
}
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
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
  gap: 14px;
  padding: 16px 4px;
  border-bottom: 1px solid var(--mx-line-soft);
  cursor: pointer;
  transition: background 0.18s var(--mx-ease);
}
.order:hover {
  background: var(--mx-line-soft);
}
.order-pic {
  width: 64px;
  height: 64px;
  border-radius: var(--mx-media-r);
  overflow: hidden;
  border: 1px solid var(--mx-line);
  flex: none;
}
.order-main {
  flex: 1;
  min-width: 0;
}
.order-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--mx-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.order-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--mx-ink-3);
  display: flex;
  gap: 8px;
}
.order-count {
  color: var(--mx-ink-2);
}
.order-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex: none;
}
.amount {
  font-size: 16px;
  color: var(--mx-ink);
}

@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .quick {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .title {
    font-size: 22px;
  }
}
</style>
