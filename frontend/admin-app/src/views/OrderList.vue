<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { adminOrderCancel, adminOrderDetail, adminOrderList, adminOrderShip } from '../api'
import { useAuthStore } from '../stores/auth'
import type { AdminOrderVO, OrderDetailVO } from '../types/api'

const auth = useAuthStore()
const router = useRouter()

const rows = ref<AdminOrderVO[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, status: '' as string })
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
    const j = await adminOrderList({
      page: query.page,
      size: query.size,
      status: query.status || undefined,
    })
    rows.value = j.data.records
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

const detailVisible = ref(false)
const detail = ref<OrderDetailVO | null>(null)

async function openDetail(row: AdminOrderVO) {
  detail.value = (await adminOrderDetail(row.id)).data
  detailVisible.value = true
}

/** ★ 发货：路径是 /api/orders/{id}/ship（C 端 Controller 里唯一挂权限码的方法） */
async function ship(row: AdminOrderVO) {
  await ElMessageBox.confirm(`确定对订单 ${row.orderNo} 执行发货？`, '提示', { type: 'warning' }).catch(
    () => null,
  )
  await adminOrderShip(row.id)
  ElMessage.success('已发货')
  load()
}

/** ★ 管理端取消仅对「待支付」生效，已支付会被后端 CAS 挡成 400 */
async function cancel(row: AdminOrderVO) {
  await ElMessageBox.confirm(`确定取消订单 ${row.orderNo}？`, '危险操作', { type: 'warning' }).catch(
    () => null,
  )
  await adminOrderCancel(row.id)
  ElMessage.success('已取消')
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <div class="bar">
        <el-select v-model="query.status" placeholder="状态（不选=全部）" clearable style="width: 160px" @change="load">
          <el-option value="PENDING_PAYMENT" label="待支付" />
          <el-option value="PAID" label="已支付" />
          <el-option value="SHIPPED" label="已发货" />
          <el-option value="COMPLETED" label="已完成" />
          <el-option value="CANCELLED" label="已取消" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" border style="margin-top: 12px">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="orderNo" label="订单号" width="200" />
        <el-table-column label="买家" width="140">
          <!-- ★ AdminOrderVO 带 userId/nickname —— 运营必须知道是谁的单 -->
          <template #default="{ row }">
            {{ row.userNickname || '-' }}
            <span class="uid">#{{ row.userId }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="payAmount" label="应付" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'CANCELLED' ? 'info' : 'success'">
              {{ STATUS_LABEL[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="receiverName" label="收货人" width="100" />
        <el-table-column prop="createdAt" label="下单时间" width="180" />
        <el-table-column label="操作" width="230">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="auth.hasPerm('order:ship') && row.status === 'PAID'"
              link
              type="success"
              @click="ship(row)"
            >
              发货
            </el-button>
            <el-button
              v-if="auth.hasPerm('order:cancel') && row.status === 'PENDING_PAYMENT'"
              link
              type="danger"
              @click="cancel(row)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.size"
        :total="total"
        layout="total, prev, pager, next"
        style="margin-top: 12px"
        @current-change="load"
      />
    </el-card>

    <el-dialog v-model="detailVisible" :title="`订单详情 #${detail?.id ?? ''}`" width="760px">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="订单号">{{ detail.orderNo }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            {{ STATUS_LABEL[detail.status] || detail.status }}
          </el-descriptions-item>
          <el-descriptions-item label="商品总额">{{ detail.totalAmount }}</el-descriptions-item>
          <el-descriptions-item label="优惠">{{ detail.discountAmount ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="应付">{{ detail.payAmount }}</el-descriptions-item>
          <el-descriptions-item label="收货人">
            {{ detail.receiverName }} {{ detail.receiverPhone }}
          </el-descriptions-item>
          <el-descriptions-item label="收货地址" :span="2">
            {{ detail.receiverAddress }}
          </el-descriptions-item>
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
          <!-- ★ 金额恒等式：total - discount = pay（与 C 端详情页同一口径） -->
          <span class="check">
            {{ detail.totalAmount }} − {{ detail.discountAmount ?? 0 }} = {{ detail.payAmount }}
          </span>
          <el-button link type="primary" @click="router.push(`/orders/${detail.id}`)">
            在整页中打开
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  gap: 10px;
}
.uid {
  color: #c0c4cc;
  font-size: 12px;
}
.foot {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.check {
  font-size: 13px;
  color: #909399;
}
</style>
