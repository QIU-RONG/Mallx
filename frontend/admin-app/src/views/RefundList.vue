<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminRefundApprove,
  adminRefundExecute,
  adminRefundList,
  adminRefundReceive,
  adminRefundReject,
} from '../api'
import { useAuthStore } from '../stores/auth'
import type { AdminRefundVO } from '../types/api'

const auth = useAuthStore()

const rows = ref<AdminRefundVO[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, size: 10, status: '' as string, userId: '' as string })

const TYPE_LABEL: Record<string, string> = {
  REFUND_ONLY: '仅退款',
  RETURN_REFUND: '退货退款',
}

/** ★ tag 类型按「是不是终态 / 是不是坏消息」分，而不是按状态名硬背 */
const STATUS_META: Record<
  string,
  { label: string; type: 'info' | 'warning' | 'primary' | 'success' | 'danger' }
> = {
  APPLIED: { label: '待审核', type: 'warning' },
  APPROVED: { label: '审核通过', type: 'primary' },
  REJECTED: { label: '已拒绝', type: 'danger' },
  RETURNING: { label: '买家已寄出', type: 'primary' },
  REFUNDING: { label: '待打款', type: 'warning' },
  SUCCESS: { label: '退款成功', type: 'success' },
  CANCELLED: { label: '已撤销', type: 'info' },
}

/**
 * ★★ 按钮显隐 = 状态机 × 权限码，两把锁都要有：
 *   - 状态机：让运营【看不见】当前做不了的动作（少一次无谓的 400）
 *   - 权限码：让没有该权限的人【根本没有按钮】（显示出来点了也是 403）
 * ⚠️ 两边都只是体验，真正的边界是后端每条 SQL 的 WHERE status = '...' 与 @PreAuthorize。
 */
const can = {
  approve: (r: AdminRefundVO) => r.status === 'APPLIED' && auth.hasPerm('refund:approve'),
  reject: (r: AdminRefundVO) => r.status === 'APPLIED' && auth.hasPerm('refund:reject'),
  receive: (r: AdminRefundVO) => r.status === 'RETURNING' && auth.hasPerm('refund:receive'),
  // 打款有两条合法起点：仅退款【审核通过】即可；退货退款必须【已收货】（REFUNDING）
  execute: (r: AdminRefundVO) =>
    ((r.status === 'APPROVED' && r.type === 'REFUND_ONLY') || r.status === 'REFUNDING') &&
    auth.hasPerm('refund:refund'),
}

async function load() {
  loading.value = true
  try {
    const j = await adminRefundList({
      page: query.page,
      size: query.size,
      status: query.status || undefined,
      userId: query.userId ? Number(query.userId) : undefined,
    })
    rows.value = j.data.records
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

/**
 * ★ 统一包一层：本项目业务失败是【HTTP 200 + body.code != 0】，403 也是常态，
 *   这两种的提示在 `api/http.ts` 的响应拦截器里已经给过了。
 *   这里只负责两件事：① 吞掉 rejection（否则控制台留 Unhandled Promise Rejection）；
 *   ② 成功后提示 + 刷新。⚠️ 千万别在这里再 ElMessage.error 一次 —— 一个错误弹两遍。
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

async function doApprove(row: AdminRefundVO) {
  await attempt(
    adminRefundApprove(row.id, '审核通过'),
    row.type === 'REFUND_ONLY' ? '已通过，可执行退款' : '已通过，等待买家寄回后确认收货',
  )
}

/** ★ 拒绝必须填原因：remark 会展示给买家，空原因 = 买家不知道为什么被拒 */
async function doReject(row: AdminRefundVO) {
  const { value } = await ElMessageBox.prompt('请填写拒绝原因（买家可见）', '审核拒绝', {
    inputPattern: /\S+/,
    inputErrorMessage: '原因不能为空',
  }).catch(() => ({ value: null as string | null }))
  if (!value) return
  await attempt(adminRefundReject(row.id, value), '已拒绝')
}

async function doReceive(row: AdminRefundVO) {
  await ElMessageBox.confirm(
    `确认已收到退货？物流单号 ${row.trackingNo || '-'}`,
    '确认收货',
    { type: 'warning' },
  ).catch(() => null)
  await attempt(adminRefundReceive(row.id), '已收货，可执行退款')
}

/** ★★★ 动钱的动作：二次确认必须写清后果，并说明它【不可撤销】 */
async function doExecute(row: AdminRefundVO) {
  await ElMessageBox.confirm(
    `将向买家退还 ¥${row.amount}，并回补库存 / 退还优惠券。\n该操作不可撤销，确定继续？`,
    '执行退款',
    { type: 'warning', confirmButtonText: '确认退款', cancelButtonText: '再想想' },
  ).catch(() => null)
  await attempt(adminRefundExecute(row.id), '退款成功')
}

// ---------------- 详情（进度时间轴） ----------------
const detailVisible = ref(false)
const detail = ref<AdminRefundVO | null>(null)

/**
 * ★ 时间轴只收【非空】的时间戳：五个时间点对应五个动作，
 * 没走到那一步就是 null —— 判空而不是假定有序，否则会出现「已完成」排在「已申请」前面。
 */
const steps = computed(() => {
  const r = detail.value
  if (!r) return []
  const raw: Array<[string, string | undefined]> = [
    ['提交申请', r.appliedAt],
    ['审核完成', r.auditedAt],
    ['买家寄出', r.shippedAt],
    ['仓库收货', r.receivedAt],
    ['退款到账', r.refundedAt],
  ]
  return raw
    .filter((x): x is [string, string] => !!x[1])
    .map(([label, time]) => ({ label, time }))
})

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <div class="bar">
        <el-select
          v-model="query.status"
          placeholder="状态（不选=全部）"
          clearable
          style="width: 170px"
          @change="load"
        >
          <el-option value="APPLIED" label="待审核" />
          <el-option value="APPROVED" label="审核通过" />
          <el-option value="RETURNING" label="买家已寄出" />
          <el-option value="REFUNDING" label="待打款" />
          <el-option value="SUCCESS" label="退款成功" />
          <el-option value="REJECTED" label="已拒绝" />
          <el-option value="CANCELLED" label="已撤销" />
        </el-select>
        <el-input
          v-model="query.userId"
          placeholder="买家 userId"
          clearable
          style="width: 160px"
          @keyup.enter="load"
        />
        <el-button type="primary" @click="load">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe style="margin-top: 12px">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="refundNo" label="售后单号" width="190" />
        <el-table-column prop="orderNo" label="订单号" width="190" />
        <el-table-column label="买家" width="130">
          <template #default="{ row }">{{ row.userNickname || '-' }}</template>
        </el-table-column>
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
        <el-table-column prop="appliedAt" label="申请时间" width="180" />
        <el-table-column label="操作" min-width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="((detail = row), (detailVisible = true))">
              详情
            </el-button>
            <el-button v-if="can.approve(row)" link type="success" @click="doApprove(row)">
              通过
            </el-button>
            <el-button v-if="can.reject(row)" link type="danger" @click="doReject(row)">
              拒绝
            </el-button>
            <el-button v-if="can.receive(row)" link type="primary" @click="doReceive(row)">
              确认收货
            </el-button>
            <el-button v-if="can.execute(row)" link type="warning" @click="doExecute(row)">
              执行退款
            </el-button>
            <!-- ★ 空状态也要说人话：退货退款在等货，运营不需要干等得莫名其妙 -->
            <span v-if="row.status === 'APPROVED' && row.type === 'RETURN_REFUND'" class="hint">
              等待买家寄回
            </span>
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

    <el-dialog v-model="detailVisible" :title="`售后详情 #${detail?.refundNo ?? ''}`" width="720px">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="售后单号">{{ detail.refundNo }}</el-descriptions-item>
          <el-descriptions-item label="订单号">{{ detail.orderNo }}</el-descriptions-item>
          <el-descriptions-item label="类型">
            {{ TYPE_LABEL[detail.type] || detail.type }}
          </el-descriptions-item>
          <el-descriptions-item label="退款额">¥{{ detail.amount }}</el-descriptions-item>
          <el-descriptions-item label="买家">{{ detail.userNickname || '-' }}</el-descriptions-item>
          <el-descriptions-item label="物流单号">{{ detail.trackingNo || '-' }}</el-descriptions-item>
          <el-descriptions-item label="申请原因" :span="2">{{ detail.reason }}</el-descriptions-item>
          <el-descriptions-item label="审核备注" :span="2">
            {{ detail.remark || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-timeline style="margin-top: 16px">
          <el-timeline-item
            v-for="s in steps"
            :key="s.label"
            :timestamp="s.time"
            placement="top"
          >
            {{ s.label }}
          </el-timeline-item>
        </el-timeline>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  gap: 10px;
}
.hint {
  color: #909399;
  font-size: 12px;
}
</style>
