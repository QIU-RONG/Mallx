<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { orderCancel, orderConfirm, orderDetail, payOrder } from '../api'
import type { OrderDetailVO, OrderStatus } from '../types/api'

const route = useRoute()
const router = useRouter()
const vo = ref<OrderDetailVO | null>(null)
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
    const j = await orderDetail(route.params.id as string)
    vo.value = j.data
  } finally {
    loading.value = false
  }
}

async function pay() {
  if (!vo.value) return
  await payOrder(vo.value.id)
  ElMessage.success('支付成功')
  load()
}

async function cancel() {
  if (!vo.value) return
  await ElMessageBox.confirm('确定取消该订单？', '取消订单', { type: 'warning' })
  await orderCancel(vo.value.id)
  ElMessage.success('已取消')
  load()
}

async function confirm() {
  if (!vo.value) return
  await ElMessageBox.confirm('确认已收到货？', '确认收货', { type: 'warning' })
  await orderConfirm(vo.value.id)
  ElMessage.success('已完成')
  load()
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="wrap">
    <el-page-header @back="router.push('/orders')" content="订单详情" />
    <template v-if="vo">
      <el-descriptions :column="2" border class="desc">
        <el-descriptions-item label="订单号">{{ vo.orderNo }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="STATUS_META[vo.status].type" size="small">
            {{ STATUS_META[vo.status].label }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="商品总额">￥{{ vo.totalAmount }}</el-descriptions-item>
        <el-descriptions-item label="优惠">
          ￥{{ vo.discountAmount }}
          <span class="hint">（实付 = 总额 − 优惠 = ￥{{ vo.payAmount }}）</span>
        </el-descriptions-item>
        <el-descriptions-item label="收货人">
          {{ vo.receiverName }} {{ vo.receiverPhone }}
        </el-descriptions-item>
        <el-descriptions-item label="收货地址">{{ vo.receiverAddress }}</el-descriptions-item>
        <el-descriptions-item label="下单时间">{{ vo.createdAt }}</el-descriptions-item>
        <el-descriptions-item label="支付时间">{{ vo.paidAt || '-' }}</el-descriptions-item>
        <el-descriptions-item label="发货时间">{{ vo.shippedAt || '-' }}</el-descriptions-item>
        <el-descriptions-item label="完成/取消">
          {{ vo.completedAt || vo.cancelledAt || '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <el-card shadow="never" style="margin-top: 16px">
        <template #header>商品明细</template>
        <el-table :data="vo.items" style="width: 100%">
          <el-table-column label="商品" min-width="240">
            <template #default="{ row }">
              <div class="cell-product">
                <img :src="row.image" class="pic" alt="" />
                <div>
                  <div>{{ row.productName }}</div>
                  <div class="hint">{{ row.skuName }}</div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="单价" width="120">
            <template #default="{ row }">￥{{ row.price }}</template>
          </el-table-column>
          <el-table-column label="数量" width="90" prop="quantity" />
          <el-table-column label="小计" width="120">
            <template #default="{ row }">￥{{ row.totalAmount }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <div class="actions">
        <el-button v-if="vo.status === 'PENDING_PAYMENT'" type="danger" @click="pay">立即支付</el-button>
        <el-button v-if="vo.status === 'PENDING_PAYMENT'" @click="cancel">取消订单</el-button>
        <el-button v-if="vo.status === 'SHIPPED'" type="success" @click="confirm">确认收货</el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1000px;
  margin: 0 auto;
  padding: 16px;
  min-height: 260px;
}
.desc {
  margin-top: 16px;
}
.cell-product {
  display: flex;
  gap: 10px;
  align-items: center;
}
.pic {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  background: #f0f0f0;
}
.hint {
  color: #909399;
  font-size: 12px;
}
.actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}
</style>
