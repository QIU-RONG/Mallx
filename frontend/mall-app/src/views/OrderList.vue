<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { orderCancel, orderConfirm, orderList, payOrder } from '../api'
import type { OrderStatus, OrderVO } from '../types/api'

const router = useRouter()
const records = ref<OrderVO[]>([])
const total = ref(0)
const current = ref(1)
const size = ref(10)
const status = ref<string>('')
const loading = ref(false)

const STATUS_META: Record<OrderStatus, { label: string; type: 'info' | 'warning' | 'primary' | 'success' | 'danger' }> = {
  PENDING_PAYMENT: { label: '待支付', type: 'warning' },
  PAID: { label: '已支付', type: 'primary' },
  SHIPPED: { label: '已发货', type: 'primary' },
  COMPLETED: { label: '已完成', type: 'success' },
  CANCELLED: { label: '已取消', type: 'info' },
}

async function load() {
  loading.value = true
  try {
    const j = await orderList({ current: current.value, size: size.value, status: status.value || undefined })
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
  await ElMessageBox.confirm(`确定取消订单 ${row.orderNo}？`, '取消订单', { type: 'warning' })
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
    <h3>我的订单</h3>

    <div class="toolbar">
      <el-select v-model="status" placeholder="全部状态" clearable style="width: 160px" @change="load">
        <el-option v-for="(m, k) in STATUS_META" :key="k" :label="m.label" :value="k" />
      </el-select>
    </div>

    <el-empty v-if="!loading && records.length === 0" description="还没有订单" />
    <el-table v-else :data="records" style="width: 100%">
      <el-table-column label="订单号" min-width="180" prop="orderNo" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="STATUS_META[row.status as OrderStatus].type" size="small">
            {{ STATUS_META[row.status as OrderStatus].label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120">
        <template #default="{ row }">
          <div>￥{{ row.payAmount }}</div>
          <div v-if="row.discountAmount > 0" class="hint">省了 ￥{{ row.discountAmount }}</div>
        </template>
      </el-table-column>
      <el-table-column label="收货人" width="160">
        <template #default="{ row }">{{ row.receiverName }} {{ row.receiverPhone }}</template>
      </el-table-column>
      <el-table-column label="下单时间" width="170" prop="createdAt" />
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/orders/${row.id}`)">详情</el-button>
          <el-button v-if="row.status === 'PENDING_PAYMENT'" link type="danger" @click="pay(row)">
            支付
          </el-button>
          <el-button v-if="row.status === 'PENDING_PAYMENT'" link @click="cancel(row)">取消</el-button>
          <el-button v-if="row.status === 'SHIPPED'" link type="success" @click="confirm(row)">
            确认收货
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="current"
      :page-size="size"
      :total="total"
      layout="prev, pager, next"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
  min-height: 260px;
}
.toolbar {
  margin-bottom: 12px;
}
.hint {
  color: #f56c6c;
  font-size: 12px;
}
</style>
