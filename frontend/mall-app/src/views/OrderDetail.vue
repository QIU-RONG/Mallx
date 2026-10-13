<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { orderCancel, orderConfirm, orderDetail, payOrder, refundApply } from '../api'
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

// ===================== 申请售后（Day 46） =====================
/**
 * ★★ 售后类型不是买家「想选哪个选哪个」，而是【订单当前状态】决定的：
 *     未发货（PAID）          → 只能 REFUND_ONLY（货还没出仓，不存在「寄回」）
 *     已发货（SHIPPED/COMPLETED）→ 只能 RETURN_REFUND（货在你手上，要退就得寄回）
 *   这是**跨对象的关系校验**，前端按状态锁定选项是【体验】，
 *   真正的守门在 RefundServiceImpl#apply（选错会 400，且报错会指明该选哪个）。
 */
const REFUNDABLE: Partial<Record<OrderStatus, 'REFUND_ONLY' | 'RETURN_REFUND'>> = {
  PAID: 'REFUND_ONLY',
  SHIPPED: 'RETURN_REFUND',
  COMPLETED: 'RETURN_REFUND',
}

const applyVisible = ref(false)
const applyReason = ref('')

const applyType = computed(() => (vo.value ? REFUNDABLE[vo.value.status] : undefined))
const applyTypeLabel = computed(() =>
  applyType.value === 'REFUND_ONLY' ? '仅退款（未发货，无需寄回）' : '退货退款（需将商品寄回）',
)

function openApply() {
  applyReason.value = ''
  applyVisible.value = true
}

async function submitApply() {
  if (!vo.value || !applyType.value) return
  if (!applyReason.value.trim()) {
    ElMessage.warning('请填写申请原因')
    return
  }
  try {
    await refundApply({
      orderId: vo.value.id,
      type: applyType.value,
      reason: applyReason.value.trim(),
    })
    ElMessage.success('已提交，可在「我的售后」查看进度')
    applyVisible.value = false
    load()
  } catch {
    /* 提示已由 http.ts 的拦截器给出（本项目业务失败是 HTTP 200 + body.code） */
  }
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
        <!-- ★ 只有「付过钱且还没退过」的订单能申请售后 -->
        <el-button v-if="applyType" @click="openApply">申请售后</el-button>
      </div>
    </template>

    <el-dialog v-model="applyVisible" title="申请售后" width="520px">
      <el-form label-width="90px">
        <el-form-item label="售后类型">
          <!-- ★ 类型由订单状态锁定：给买家一个「不可选」的选择框，比让他选错再吃 400 强 -->
          <el-input :model-value="applyTypeLabel" readonly />
        </el-form-item>
        <el-form-item label="申请原因" required>
          <el-input
            v-model="applyReason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="请说明申请原因（200 字以内）"
          />
        </el-form-item>
      </el-form>
      <div class="hint">
        退款金额由系统按订单实付金额（￥{{ vo?.payAmount }}）计算，不支持自行填写。
      </div>
      <template #footer>
        <el-button @click="applyVisible = false">取消</el-button>
        <el-button type="primary" @click="submitApply">提交申请</el-button>
      </template>
    </el-dialog>
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
