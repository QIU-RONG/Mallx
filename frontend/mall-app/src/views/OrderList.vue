<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { orderCancel, orderConfirm, orderList, payOrder } from '../api'
import ProductThumb from '../components/ProductThumb.vue'
import type { OrderStatus, OrderVO } from '../types/api'

/**
 * 我的订单（Day 65 改版）。
 *
 * <p>★★ 用户原话：「应该直接看到的是商品，而不是订单编号」——
 * 列表主体从「订单号 + 收货人」改成【商品卡】：缩略图 + 商品名 + 规格 + 件数，
 * 订单号退出首屏（详情页里还有，客服对账仍可用）。
 *
 * <p>★ 摘要不是前端 N+1 查出来的：后端 OrderVO 带 firstItemName/Image/ItemCount，
 * 一次 IN 查询批量补（见 OrderServiceImpl#fillFirstItem）。
 */
const router = useRouter()
const records = ref<OrderVO[]>([])
const total = ref(0)
const current = ref(1)
const size = ref(10)
const status = ref<string>('')
const loading = ref(false)

function fmtTime(s?: string) {
  return s ? s.replace('T', ' ').slice(0, 16) : '-'
}

const STATUS_META: Record<OrderStatus, { label: string; type: 'info' | 'warning' | 'primary' | 'success' | 'danger' }> = {
  PENDING_PAYMENT: { label: '待支付', type: 'warning' },
  PAID: { label: '待发货', type: 'primary' },
  SHIPPED: { label: '待收货', type: 'primary' },
  COMPLETED: { label: '已完成', type: 'success' },
  CANCELLED: { label: '已取消', type: 'info' },
}

async function load() {
  loading.value = true
  try {
    const j = await orderList({ page: current.value, size: size.value, status: status.value || undefined })
    records.value = j.data.records || []
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

async function pay(row: OrderVO) {
  await payOrder(row.id)
  ElMessage.success('支付成功')
  load()
}

async function cancel(row: OrderVO) {
  await ElMessageBox.confirm('确定取消该订单？', '取消订单', { type: 'warning' })
  await orderCancel(row.id)
  ElMessage.success('已取消')
  load()
}

async function confirm(row: OrderVO) {
  await ElMessageBox.confirm('确认已收到货？', '确认收货', { type: 'warning' })
  await orderConfirm(row.id)
  ElMessage.success('已完成')
  load()
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="wrap">
    <div class="head">
      <h3>我的订单</h3>
      <el-select v-model="status" placeholder="全部状态" clearable style="width: 150px" @change="load">
        <el-option v-for="(m, k) in STATUS_META" :key="k" :label="m.label" :value="k" />
      </el-select>
    </div>

    <el-empty v-if="!loading && records.length === 0" description="还没有订单，去逛逛吧">
      <el-button type="primary" @click="router.push('/')">去商城</el-button>
    </el-empty>

    <ul v-else class="orders">
      <li v-for="r in records" :key="r.id" class="order">
        <div class="order-head">
          <span class="time">{{ fmtTime(r.createdAt) }}</span>
          <el-tag :type="STATUS_META[r.status].type" size="small" effect="plain">
            {{ STATUS_META[r.status].label }}
          </el-tag>
        </div>

        <div class="order-body" @click="router.push(`/orders/${r.id}`)">
          <div class="pic">
            <ProductThumb :src="r.firstItemImage" :name="r.firstItemName || '订单商品'" :seed="r.id" />
          </div>
          <div class="main">
            <div class="name">{{ r.firstItemName || '订单商品' }}</div>
            <div class="sub">
              <span v-if="r.firstItemSkuName">{{ r.firstItemSkuName }}</span>
              <span v-if="(r.itemCount ?? 0) > 1" class="count">等 {{ r.itemCount }} 件</span>
            </div>
          </div>
          <div class="side">
            <div class="amount mx-serif">¥{{ Number(r.payAmount).toFixed(2) }}</div>
            <div v-if="Number(r.discountAmount) > 0" class="discount">省了 ¥{{ r.discountAmount }}</div>
          </div>
        </div>

        <div class="order-actions">
          <el-button link type="primary" @click="router.push(`/orders/${r.id}`)">详情</el-button>
          <el-button v-if="r.status === 'PENDING_PAYMENT'" link type="primary" @click="pay(r)">支付</el-button>
          <el-button v-if="r.status === 'PENDING_PAYMENT'" link @click="cancel(r)">取消</el-button>
          <el-button v-if="r.status === 'SHIPPED'" link type="success" @click="confirm(r)">确认收货</el-button>
        </div>
      </li>
    </ul>

    <el-pagination
      v-model:current-page="current"
      :page-size="size"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 24px"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.wrap {
  min-height: 320px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.head h3 {
  margin: 0;
}
.orders {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--mx-line);
}
.order {
  padding: 14px 4px 10px;
  border-bottom: 1px solid var(--mx-line-soft);
}
.order-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--mx-ink-3);
}
.order-body {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 10px;
  cursor: pointer;
}
.pic {
  width: 64px;
  height: 64px;
  border-radius: var(--mx-media-r);
  overflow: hidden;
  border: 1px solid var(--mx-line);
  flex: none;
}
.main {
  flex: 1;
  min-width: 0;
}
.name {
  font-size: 14px;
  font-weight: 600;
  color: var(--mx-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--mx-ink-3);
  display: flex;
  gap: 8px;
}
.count {
  color: var(--mx-ink-2);
}
.side {
  text-align: right;
  flex: none;
}
.amount {
  font-size: 16px;
  color: var(--mx-ink);
}
.discount {
  margin-top: 4px;
  font-size: 12px;
  color: var(--mx-accent);
}
.order-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 6px;
}
</style>
