<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { myRefunds, refundCancel, refundShip } from '../api'
import type { RefundVO } from '../types/api'

const rows = ref<RefundVO[]>([])
const total = ref(0)
const current = ref(1)
const size = ref(10)
const loading = ref(false)

const TYPE_LABEL: Record<string, string> = {
  REFUND_ONLY: '仅退款',
  RETURN_REFUND: '退货退款',
}

const STATUS_META: Record<
  string,
  { label: string; type: 'info' | 'warning' | 'primary' | 'success' | 'danger'; hint: string }
> = {
  APPLIED: { label: '待审核', type: 'warning', hint: '商家正在处理，请耐心等待' },
  APPROVED: { label: '审核通过', type: 'primary', hint: '请按提示寄回商品并填写物流单号' },
  REJECTED: { label: '已拒绝', type: 'danger', hint: '商家拒绝了本次申请，可查看拒绝原因' },
  RETURNING: { label: '已寄出', type: 'primary', hint: '商家收到货后会为你退款' },
  REFUNDING: { label: '退款中', type: 'warning', hint: '款项将退回原支付账户' },
  SUCCESS: { label: '退款成功', type: 'success', hint: '退款已完成' },
  CANCELLED: { label: '已撤销', type: 'info', hint: '你撤销了本次申请' },
}

/**
 * ★ 与 http.ts 的分工同 admin-app：业务失败（HTTP 200 + code!=0）的提示由拦截器给过，
 *   这里只吞 rejection + 成功后刷新，避免一个错误弹两遍。
 */
async function attempt(p: Promise<unknown>, okMsg: string) {
  try {
    await p
    ElMessage.success(okMsg)
    load()
  } catch {
    /* 提示已由拦截器给出 */
  }
}

async function load() {
  loading.value = true
  try {
    const j = await myRefunds({ page: current.value, size: size.value })
    rows.value = j.data.records || []
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

async function cancel(row: RefundVO) {
  await ElMessageBox.confirm('确定撤销这笔售后申请？', '撤销申请', { type: 'warning' }).catch(
    () => null,
  )
  await attempt(refundCancel(row.id), '已撤销')
}

/** ★ 只有【退货退款】在【审核通过】后才填物流单号 —— 与后端 ship() 的守卫同一条规则 */
async function ship(row: RefundVO) {
  const { value } = await ElMessageBox.prompt('请填写退货的物流单号', '我已寄出', {
    inputPattern: /\S+/,
    inputErrorMessage: '物流单号不能为空',
  }).catch(() => ({ value: null as string | null }))
  if (!value) return
  await attempt(refundShip(row.id, value), '已提交，等待商家收货')
}

// ---------------- 详情（进度） ----------------
const detailVisible = ref(false)
const detail = ref<RefundVO | null>(null)

/** ★ 只收非空时间戳：没走到那一步就是 null，判空而不是假定有序 */
const steps = computed(() => {
  const r = detail.value
  if (!r) return []
  const raw: Array<[string, string | undefined]> = [
    ['提交申请', r.appliedAt],
    ['商家审核', r.auditedAt],
    ['你已寄出', r.shippedAt],
    ['商家收货', r.receivedAt],
    ['退款到账', r.refundedAt],
  ]
  return raw.filter((x): x is [string, string] => !!x[1]).map(([label, time]) => ({ label, time }))
})

onMounted(load)
</script>

<template>
  <div class="wrap">
    <h3>我的售后</h3>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="refundNo" label="售后单号" width="180" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.type === 'RETURN_REFUND' ? 'warning' : 'info'">
            {{ TYPE_LABEL[row.type] || row.type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="退款额" width="100" />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="STATUS_META[row.status]?.type || 'info'">
            {{ STATUS_META[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="200">
        <template #default="{ row }">
          <div>{{ STATUS_META[row.status]?.hint || '-' }}</div>
          <!-- ★ 拒绝原因必须显眼：买家不知道为什么被拒，就会反复申请 -->
          <div v-if="row.status === 'REJECTED' && row.remark" class="remark">
            拒绝原因：{{ row.remark }}
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="appliedAt" label="申请时间" width="180" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button link type="primary" @click="((detail = row), (detailVisible = true))">
            进度
          </el-button>
          <el-button
            v-if="row.status === 'APPROVED' && row.type === 'RETURN_REFUND'"
            link
            type="success"
            @click="ship(row)"
          >
            我已寄出
          </el-button>
          <el-button
            v-if="row.status === 'APPLIED' || row.status === 'APPROVED'"
            link
            @click="cancel(row)"
          >
            撤销
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <span class="empty">还没有售后记录</span>
      </template>
    </el-table>

    <el-pagination
      v-model:current-page="current"
      v-model:page-size="size"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 12px"
      @current-change="load"
    />

    <el-dialog v-model="detailVisible" :title="`售后进度 #${detail?.refundNo ?? ''}`" width="620px">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="类型">
            {{ TYPE_LABEL[detail.type] || detail.type }}
          </el-descriptions-item>
          <el-descriptions-item label="退款额">¥{{ detail.amount }}</el-descriptions-item>
          <el-descriptions-item label="申请原因" :span="2">{{ detail.reason }}</el-descriptions-item>
          <el-descriptions-item label="商家备注" :span="2">
            {{ detail.remark || '-' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.trackingNo" label="物流单号" :span="2">
            {{ detail.trackingNo }}
          </el-descriptions-item>
        </el-descriptions>

        <el-timeline style="margin-top: 16px">
          <el-timeline-item v-for="s in steps" :key="s.label" :timestamp="s.time" placement="top">
            {{ s.label }}
          </el-timeline-item>
        </el-timeline>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px;
}
.remark {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 2px;
}
.empty {
  color: #909399;
}
</style>
