<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminOrderDetail, adminOrderShip } from '../api'
import type { OrderDetailVO } from '../types/api'

const route = useRoute()
const router = useRouter()

const detail = ref<OrderDetailVO | null>(null)
const loading = ref(false)

const STATUS_LABEL: Record<string, string> = {
  PENDING_PAYMENT: '待支付',
  PAID: '已支付',
  SHIPPED: '已发货',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
}

async function load() {
  loading.value = true
  try {
    detail.value = (await adminOrderDetail(route.params.id as string)).data
  } finally {
    loading.value = false
  }
}

async function ship() {
  await adminOrderShip(route.params.id as string)
  ElMessage.success('已发货')
  load()
}

onMounted(load)
</script>

<template>
  <el-card v-loading="loading" shadow="never">
    <template v-if="detail">
      <div class="head">
        <h3>订单 #{{ detail.id }} · {{ detail.orderNo }}</h3>
        <el-tag>{{ STATUS_LABEL[detail.status] || detail.status }}</el-tag>
      </div>

      <el-descriptions :column="2" border style="margin-top: 12px">
        <el-descriptions-item label="商品总额">{{ detail.totalAmount }}</el-descriptions-item>
        <el-descriptions-item label="优惠">{{ detail.discountAmount ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="应付">{{ detail.payAmount }}</el-descriptions-item>
        <el-descriptions-item label="买家 id">{{ detail.userId ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="收货人">
          {{ detail.receiverName }} {{ detail.receiverPhone }}
        </el-descriptions-item>
        <el-descriptions-item label="收货地址">{{ detail.receiverAddress }}</el-descriptions-item>
        <el-descriptions-item label="下单">{{ detail.createdAt }}</el-descriptions-item>
        <el-descriptions-item label="支付">{{ detail.paidAt || '-' }}</el-descriptions-item>
        <el-descriptions-item label="发货">{{ detail.shippedAt || '-' }}</el-descriptions-item>
        <el-descriptions-item label="完成">{{ detail.completedAt || '-' }}</el-descriptions-item>
      </el-descriptions>

      <el-table :data="detail.items" border style="margin-top: 12px">
        <el-table-column prop="productName" label="商品" min-width="180" />
        <el-table-column prop="skuName" label="规格" width="140" />
        <el-table-column prop="price" label="单价" width="100" />
        <el-table-column prop="quantity" label="数量" width="80" />
      </el-table>

      <div class="foot">
        <el-button @click="router.back()">返回列表</el-button>
        <el-button v-if="detail.status === 'PAID'" type="primary" @click="ship">发货</el-button>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
h3 {
  margin: 0;
}
.foot {
  margin-top: 16px;
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
</style>
