<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createReview, orderCancel, orderConfirm, orderDetail, payOrder, refundApply } from '../api'
import type { OrderDetailVO, OrderItemVO, OrderStatus } from '../types/api'
import ProductThumb from '../components/ProductThumb.vue'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${auth.token}` }))
const vo = ref<OrderDetailVO | null>(null)
const loading = ref(false)

const STATUS_META: Record<OrderStatus, { label: string; type: 'info' | 'warning' | 'primary' | 'success' | 'danger' }> = {
  PENDING_PAYMENT: { label: '待支付', type: 'warning' },
  PAID: { label: '已支付', type: 'primary' },
  SHIPPED: { label: '已发货', type: 'primary' },
  COMPLETED: { label: '已完成', type: 'success' },
  CANCELLED: { label: '已取消', type: 'info' },
  REFUNDED: { label: '已退款', type: 'info' },
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

// ===================== 评价（Day 61） =====================
/**
 * ★ 只能评【已完成的订单】里的明细，而且一条明细只能评一次 ——
 *   这两条都在后端守（GET buyContext 校验状态 + reviews 表的唯一约束）：
 *   前端这里只是「不给用户一个注定失败的按钮」。
 */
const reviewVisible = ref(false)
const reviewItem = ref<OrderItemVO | null>(null)
const reviewRating = ref(5)
const reviewContent = ref('')
const reviewImages = ref<string[]>([])
const reviewUploading = ref(false)
const reviewSubmitting = ref(false)

function onReviewImageUploaded(res: { code?: number; message?: string; data?: string }) {
  reviewUploading.value = false
  if (res?.code === 200 && res.data) {
    reviewImages.value.push(res.data)
  } else {
    ElMessage.error(res?.message || '图片上传失败')
  }
}
function onReviewImageError() {
  reviewUploading.value = false
  ElMessage.error('图片上传失败（≤2MB，jpg/png/webp/gif）')
}
function removeReviewImage(i: number) {
  reviewImages.value.splice(i, 1)
}

function openReview(row: OrderItemVO) {
  reviewItem.value = row
  reviewRating.value = 5
  reviewContent.value = ''
  reviewImages.value = []
  reviewVisible.value = true
}

async function submitReview() {
  if (!reviewItem.value) return
  if (!reviewRating.value) {
    ElMessage.warning('请先打分')
    return
  }
  reviewSubmitting.value = true
  try {
    await createReview(reviewItem.value.id, reviewRating.value, reviewContent.value.trim(), reviewImages.value)
    ElMessage.success('评价成功，感谢反馈')
    reviewVisible.value = false
  } catch {
    /* 「已评价过」/ 网络错误：拦截器已提示 */
  } finally {
    reviewSubmitting.value = false
  }
}

// ===================== 申请售后（Day 46 / Day 71 可选类型） =====================
/**
 * ★ 售后类型按【订单状态】给候选，买家在候选里选：
 *     未发货（PAID）     → 仅退款
 *     已发货（SHIPPED）  → 仅退款（没收到/拒收）或 退货退款（已收到，寄回）
 *     已完成（COMPLETED）→ 退货退款（已经签收，不寄回等于白送）
 *   前端只做「不给注定失败的选项」；真正的守门仍在 RefundServiceImpl#apply。
 */
type RefundTypeCode = 'REFUND_ONLY' | 'RETURN_REFUND'

const REFUND_OPTIONS: Array<{ value: RefundTypeCode; label: string; hint: string }> = [
  { value: 'REFUND_ONLY', label: '仅退款', hint: '未发货，或已发货但没收到货（拒收）' },
  { value: 'RETURN_REFUND', label: '退货退款', hint: '已经收到货，需要把商品寄回' },
]

const allowedTypes = computed<RefundTypeCode[]>(() => {
  switch (vo.value?.status) {
    case 'PAID':
      return ['REFUND_ONLY']
    case 'SHIPPED':
      return ['REFUND_ONLY', 'RETURN_REFUND']
    case 'COMPLETED':
      return ['RETURN_REFUND']
    default:
      return []
  }
})

const applyAvailable = computed(() => allowedTypes.value.length > 0)
const typeOptions = computed(() => REFUND_OPTIONS.filter((o) => allowedTypes.value.includes(o.value)))
const applyType = ref<RefundTypeCode>('REFUND_ONLY')

const applyTypeHint = computed(
  () => REFUND_OPTIONS.find((o) => o.value === applyType.value)?.hint ?? '',
)

const applyVisible = ref(false)
const applyReason = ref('')

function openApply() {
  // 默认选「能退货退款就选它」—— 已签收的商品，仅退款几乎都不是本意
  applyType.value = allowedTypes.value.includes('RETURN_REFUND') ? 'RETURN_REFUND' : 'REFUND_ONLY'
  applyReason.value = ''
  applyVisible.value = true
}

async function submitApply() {
  if (!vo.value || !applyAvailable.value) return
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
        <el-descriptions-item label="商品总额">¥{{ vo.totalAmount }}</el-descriptions-item>
        <el-descriptions-item label="优惠">
          ¥{{ vo.discountAmount }}
          <span class="hint">（实付 = 总额 − 优惠 = ¥{{ vo.payAmount }}）</span>
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
                <div class="pic">
                  <ProductThumb :src="row.image" :name="row.productName" :seed="row.skuId" />
                </div>
                <div>
                  <div>{{ row.productName }}</div>
                  <div class="hint">{{ row.skuName }}</div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="单价" width="120">
            <template #default="{ row }">¥{{ row.price }}</template>
          </el-table-column>
          <el-table-column label="数量" width="90" prop="quantity" />
          <el-table-column label="小计" width="120">
            <template #default="{ row }">¥{{ row.totalAmount }}</template>
          </el-table-column>
          <el-table-column v-if="vo.status === 'COMPLETED'" label="评价" width="100">
            <template #default="{ row }">
              <el-button link type="primary" @click="openReview(row)">评价</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <div class="actions">
        <el-button v-if="vo.status === 'PENDING_PAYMENT'" type="primary" @click="pay">立即支付</el-button>
        <el-button v-if="vo.status === 'PENDING_PAYMENT'" @click="cancel">取消订单</el-button>
        <el-button v-if="vo.status === 'SHIPPED'" type="success" @click="confirm">确认收货</el-button>
        <!-- ★ 只有「付过钱且还没退过」的订单能申请售后 -->
        <el-button v-if="applyAvailable" @click="openApply">申请售后</el-button>
      </div>
    </template>

    <el-dialog v-model="applyVisible" title="申请售后" width="520px">
      <el-form label-width="90px">
        <el-form-item label="售后类型">
          <!-- Day 71：按订单状态给候选，买家自己选（已发货可二选一） -->
          <el-select v-model="applyType" style="width: 100%">
            <el-option
              v-for="o in typeOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
          <div class="type-hint">{{ applyTypeHint }}</div>
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
        退款金额由系统按订单实付金额（¥{{ vo?.payAmount }}）计算，不支持自行填写。
      </div>
      <template #footer>
        <el-button @click="applyVisible = false">取消</el-button>
        <el-button type="primary" @click="submitApply">提交申请</el-button>
      </template>
    </el-dialog>

    <!-- 评价（Day 61） -->
    <el-dialog v-model="reviewVisible" title="评价商品" width="520px">
      <div v-if="reviewItem" class="review-product">
        <div class="pic">
          <ProductThumb :src="reviewItem.image" :name="reviewItem.productName" :seed="reviewItem.skuId" />
        </div>
        <div>
          <div class="review-name">{{ reviewItem.productName }}</div>
          <div class="hint">{{ reviewItem.skuName }}</div>
        </div>
      </div>
      <el-form label-position="top">
        <el-form-item label="评分">
          <el-rate v-model="reviewRating" />
        </el-form-item>
        <el-form-item label="评价内容">
          <el-input
            v-model="reviewContent"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            placeholder="说说这件商品怎么样（可选）"
          />
        </el-form-item>
        <!-- Day 80：晒图（最多 3 张，≤2MB） -->
        <el-form-item label="晒图（可选）">
          <div class="review-upload">
            <div v-for="(img, i) in reviewImages" :key="img" class="thumb-box">
              <img :src="img" alt="" />
              <button class="thumb-x" type="button" @click="removeReviewImage(i)">×</button>
            </div>
            <el-upload
              v-if="reviewImages.length < 3"
              action="/api/upload/image"
              :headers="uploadHeaders"
              :show-file-list="false"
              accept="image/jpeg,image/png,image/webp,image/gif"
              :on-success="onReviewImageUploaded"
              :on-error="onReviewImageError"
            >
              <el-button :loading="reviewUploading">上传图片</el-button>
            </el-upload>
          </div>
          <div class="hint">支持 jpg / png / webp / gif，单张 ≤ 2MB，最多 3 张</div>
        </el-form-item>
      </el-form>
      <div class="hint">评价会展示在商品详情页，提交后不可修改。</div>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button type="primary" :loading="reviewSubmitting" @click="submitReview">提交评价</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1200px;
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
  border-radius: var(--mx-media-r);
  overflow: hidden;
  border: 1px solid var(--mx-line);
}
.hint {
  color: var(--mx-ink-3);
  font-size: 12px;
}
.type-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--mx-ink-3);
}

/* 评价弹窗里的商品行（与明细行同一套视觉） */
.review-product {
  display: flex;
  gap: 10px;
  align-items: center;
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--mx-line-soft);
}
.review-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--mx-ink);
}
.review-upload {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.thumb-box {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--mx-line);
}
.thumb-box img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-x {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}
.actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}
</style>
