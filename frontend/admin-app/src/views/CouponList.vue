<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminCouponCreate, adminCouponDelete, adminCouponEnd, adminCouponList } from '../api'
import { useAuthStore } from '../stores/auth'
import { buildCouponPayload, couponFaceText } from '../utils/coupon'
import { confirmAction } from '../utils/confirm'
import type { CouponVO } from '../types/api'

/**
 * 优惠券管理（Day 54）。
 *
 * <p>★★ 后端只有三个端点：列表 / 新建 / 删除 —— <b>没有「改券」</b>，这是决策不是缺口：
 * 券一旦发出去，改面额会和已领取用户的预期冲突（他领的是「满 100 减 20」）。
 * 真实系统的做法是「作废旧券 + 新建一张」，所以界面也不做编辑入口。
 *
 * <p>★ 分页参数叫 `page` 而不是 `current`（券的 Controller 与其它模块用的不是同一套），
 * 照着后端签名写。
 */
const auth = useAuthStore()

const rows = ref<CouponVO[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, size: 10, status: null as number | null })

async function load() {
  loading.value = true
  try {
    const j = await adminCouponList({ page: query.page, size: query.size, status: query.status })
    rows.value = j.data.records
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

function fmt(t?: string) {
  return t ? t.replace('T', ' ').slice(0, 16) : '-'
}

// ---------------- 新建 ----------------
const createVisible = ref(false)
// ★ 页面内用「一定有值」的数字：el-input-number 的 modelValue 是 number | undefined，
//   绑 null 过不了 vue-tsc。空的语义（未填 / 无门槛）在提交时由 buildCouponPayload 判。
const form = reactive({
  name: '',
  type: 'FIXED' as 'FIXED' | 'DISCOUNT',
  discountAmount: 20,
  discountRate: 0.8,
  minAmount: 0,
  totalCount: 100,
  timeRange: null as [string, string] | null,
})

function openCreate() {
  Object.assign(form, {
    name: '',
    type: 'FIXED',
    discountAmount: 20,
    // ★ 故意保留另一类型的旧值：提交时由 buildCouponPayload 按类型丢弃，
    //   这样即使以后有人把这里「清空」的逻辑删了，也不会把两个面额一起发出去。
    discountRate: 0.8,
    minAmount: 0,
    totalCount: 100,
    timeRange: null,
  })
  createVisible.value = true
}

async function submitCreate() {
  const r = buildCouponPayload(form)
  if (!r.ok) {
    ElMessage.warning(r.error)
    return
  }
  try {
    await adminCouponCreate(r.payload)
    ElMessage.success('优惠券已创建')
    createVisible.value = false
    query.page = 1
    await load()
  } catch {
    /* 无权限 / 关系校验失败：拦截器已提示 */
  }
}

async function endCoupon(row: CouponVO) {
  await confirmAction(`提前结束「${row.name}」？已领取的券不受影响，只是不能再领。`, {
    title: '提前结束',
    confirmButtonText: '结束发放',
    type: 'warning',
  })
  await adminCouponEnd(row.id)
  ElMessage.success('已结束发放')
  load()
}

async function remove(row: CouponVO) {
  const ok = await confirmAction(
    `确定删除「${row.name}」？\n已被领取过的券删不掉（后端会拒绝），已领的券不受影响。`,
    { title: '删除优惠券', confirmButtonText: '删除', type: 'error' },
  )
  if (!ok) return
  try {
    await adminCouponDelete(row.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 被 user_coupons 引用 / 无权限：拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="bar">
      <el-select
        v-model="query.status"
        placeholder="状态（不选=全部）"
        clearable
        style="width: 160px"
        @change="((query.page = 1), load())"
      >
        <el-option :value="1" label="可领取" />
        <el-option :value="0" label="已下架" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <span class="spacer" />
      <el-button v-if="auth.hasPerm('coupon:create')" type="primary" @click="openCreate">
        新建优惠券
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="券名" min-width="180" show-overflow-tooltip />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.type === 'FIXED' ? 'warning' : 'primary'">
            {{ row.type === 'FIXED' ? '满减' : '折扣' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="面额" width="100" align="right">
        <template #default="{ row }">
          <span class="money-num">{{ couponFaceText(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="使用门槛" width="110" align="right">
        <template #default="{ row }">
          {{ row.minAmount == null || Number(row.minAmount) === 0 ? '无门槛' : `满 ¥${row.minAmount}` }}
        </template>
      </el-table-column>
      <el-table-column label="已领 / 总量" width="120" align="center">
        <template #default="{ row }">{{ row.receivedCount }} / {{ row.totalCount }}</template>
      </el-table-column>
      <el-table-column label="有效期" width="250">
        <template #default="{ row }">{{ fmt(row.startTime) }} ~ {{ fmt(row.endTime) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'">
            {{ row.status === 1 ? '可领' : '下架' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 1 && auth.hasPerm('coupon:create')"
            link
            type="warning"
            @click="endCoupon(row)"
          >
            提前结束
          </el-button>
          <el-button v-if="auth.hasPerm('coupon:delete')" link type="danger" @click="remove(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="还没有优惠券">
          <el-button v-if="auth.hasPerm('coupon:create')" type="primary" @click="openCreate">
            创建第一张券
          </el-button>
        </el-empty>
      </template>
    </el-table>

    <el-pagination
      v-model:current-page="query.page"
      v-model:page-size="query.size"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 12px"
      @current-change="load"
    />

    <el-dialog v-model="createVisible" title="新建优惠券" width="560px">
      <el-form label-width="100px">
        <el-form-item label="券名" required>
          <el-input v-model="form.name" maxlength="100" placeholder="例：全场满 100 减 20" />
        </el-form-item>
        <el-form-item label="券类型">
          <!-- ★ 切换类型不清空另一侧输入：提交时由 buildCouponPayload 按类型只发一个 -->
          <el-radio-group v-model="form.type">
            <el-radio value="FIXED">满减</el-radio>
            <el-radio value="DISCOUNT">折扣</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.type === 'FIXED'" label="满减面额" required>
          <el-input-number v-model="form.discountAmount" :min="0.01" :precision="2" />
          <span class="hint inline">元</span>
        </el-form-item>
        <el-form-item v-else label="折扣率" required>
          <el-input-number v-model="form.discountRate" :min="0.01" :max="1" :step="0.05" :precision="2" />
          <span class="hint inline">0.80 = 打 8 折（实付 80%）</span>
        </el-form-item>
        <el-form-item label="使用门槛">
          <el-input-number v-model="form.minAmount" :min="0" :precision="2" />
          <span class="hint inline">0 = 无门槛</span>
        </el-form-item>
        <el-form-item label="发行总量" required>
          <el-input-number v-model="form.totalCount" :min="0" :precision="0" />
          <span class="hint inline">0 = 先占位、暂不可领</span>
        </el-form-item>
        <el-form-item label="可领时间" required>
          <el-date-picker
            v-model="form.timeRange"
            type="datetimerange"
            value-format="YYYY-MM-DDTHH:mm:ss"
            start-placeholder="开始"
            end-placeholder="结束"
            style="width: 100%"
          />
          <div class="hint">★ 存库是本地时间（LocalDateTime），不带时区</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.bar {
  display: flex;
  gap: 10px;
  align-items: center;
}
.spacer {
  flex: 1;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint.inline {
  margin-left: 10px;
}
</style>
