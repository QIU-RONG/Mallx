<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminReviewPage, adminReviewUpdateStatus } from '../api'
import { useAuthStore } from '../stores/auth'
import { confirmAction } from '../utils/confirm'
import type { AdminReviewVO } from '../types/api'

/**
 * 评价审核（Day 55）。
 *
 * <p>★★ 这是 C 端评价链路（Day 16）缺的最后一块：评价被举报、或内容违规时，
 * 平台此前<b>没有任何处理手段</b>，只能直接改库。
 *
 * <p>★ 本页做的<b>不是删除</b>：置 status=0 之后，这条评价
 * 立刻从「商品页评价列表 / 平均分 / 评价总数」里消失，但数据还在、可以恢复。
 * 反过来，恢复（置 1）后三处会同时回来 —— 因为 C 端那两个聚合本来就是实时算的，
 * 没有第二份数据要同步。
 *
 * <p>⚠️ 权限分发是刻意的：`review:list` 超管 + 商品管理员（看）；
 * `review:status` <b>只给超管</b>（改）—— 隐藏评价会直接改写商品页的展示与评分，
 * 属于以平台身份处理用户表达，与「禁用账号」同级。
 */
const auth = useAuthStore()

const rows = ref<AdminReviewVO[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({
  current: 1,
  size: 10,
  productId: '' as string,
  rating: null as number | null,
  status: null as number | null,
})

async function load() {
  loading.value = true
  try {
    const j = await adminReviewPage({
      current: query.current,
      size: query.size,
      // ★ 空串必须变成 undefined：后端 Long productId 收到 "" 会 400
      productId: query.productId ? Number(query.productId) : null,
      rating: query.rating,
      status: query.status,
    })
    rows.value = j.data.records
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

function search() {
  query.current = 1
  load()
}

function resetQuery() {
  query.productId = ''
  query.rating = null
  query.status = null
  search()
}

/** 隐藏 / 恢复。★ 两个方向都要二次确认：恢复一条被隐藏的评价同样是「替平台做决定」 */
async function toggleStatus(row: AdminReviewVO) {
  const hide = row.status === 1
  const ok = await confirmAction(
    hide
      ? `确定隐藏这条评价？\n它将从商品页评价列表、平均分与评价总数中同时消失（数据保留，可恢复）。`
      : `确定恢复这条评价？\n它会重新出现在商品页，并重新计入平均分与评价总数。`,
    {
      title: hide ? '隐藏评价' : '恢复评价',
      type: hide ? 'warning' : 'info',
      confirmButtonText: hide ? '隐藏' : '恢复',
    },
  )
  if (!ok) return
  try {
    await adminReviewUpdateStatus(row.id, hide ? 0 : 1)
    ElMessage.success(hide ? '已隐藏' : '已恢复')
    await load()
  } catch {
    /* 无 review:status / 评价不存在：拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="bar">
      <el-input
        v-model="query.productId"
        placeholder="商品 id"
        clearable
        style="width: 140px"
        @keyup.enter="search"
        @clear="search"
      />
      <el-select
        v-model="query.rating"
        placeholder="评分（不选=全部）"
        clearable
        style="width: 150px"
        @change="search"
      >
        <el-option v-for="n in 5" :key="n" :value="6 - n" :label="`${6 - n} 星`" />
      </el-select>
      <el-select
        v-model="query.status"
        placeholder="状态（不选=全部）"
        clearable
        style="width: 150px"
        @change="search"
      >
        <el-option :value="1" label="正常显示" />
        <el-option :value="0" label="已隐藏" />
      </el-select>
      <el-button type="primary" @click="search">查询</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="商品" min-width="220">
        <template #default="{ row }">
          <div class="product">
            <img v-if="row.image" :src="row.image" class="thumb" alt="" />
            <span v-else class="thumb thumb-none">—</span>
            <div class="product-text">
              <div class="product-name">{{ row.productName || `#${row.productId}` }}</div>
              <div class="product-sku">{{ row.skuName || '-' }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="评分" width="150">
        <!-- ★ 只读星级：评价的分数是 1..5 的离散值，用文字「4 星」也行，
             但星级能一眼扫出「这批评价整体偏低」 -->
        <template #default="{ row }">
          <el-rate :model-value="row.rating" disabled size="small" />
        </template>
      </el-table-column>
      <el-table-column label="晒图" width="150">
        <template #default="{ row }">
          <div v-if="row.images?.length" class="review-imgs">
            <el-image
              v-for="(u, i) in row.images"
              :key="i"
              :src="u"
              :preview-src-list="row.images"
              :initial-index="i"
              fit="cover"
              class="review-img"
              preview-teleported
            />
          </div>
          <span v-else class="muted">无</span>
        </template>
      </el-table-column>
      <el-table-column prop="content" label="内容" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">{{ row.content || '（无文字）' }}</template>
      </el-table-column>
      <el-table-column prop="userNickname" label="评价人" width="120">
        <template #default="{ row }">{{ row.userNickname || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'">
            {{ row.status === 1 ? '显示' : '已隐藏' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="createdAt" label="评价时间" width="170" />
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="auth.hasPerm('review:status')"
            link
            :type="row.status === 1 ? 'danger' : 'success'"
            @click="toggleStatus(row)"
          >
            {{ row.status === 1 ? '隐藏' : '恢复' }}
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="没有匹配的评价">
          <el-button
            v-if="query.productId || query.rating != null || query.status != null"
            size="small"
            @click="resetQuery"
          >
            清除筛选
          </el-button>
        </el-empty>
      </template>
    </el-table>

    <el-pagination
      v-model:current-page="query.current"
      v-model:page-size="query.size"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 12px"
      @current-change="load"
    />

    <div class="hint">
      ★ 隐藏不删数据：商品页列表、平均分、评价总数会同时不再计入；恢复后三处一起回来。
    </div>
  </el-card>
</template>

<style scoped>
.review-imgs {
  display: flex;
  gap: 4px;
}
.review-img {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  border: 1px solid var(--el-border-color);
}
.muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.bar {
  display: flex;
  gap: 10px;
  align-items: center;
}
.product {
  display: flex;
  gap: 8px;
  align-items: center;
}
.thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: var(--brand-radius-sm);
  background: var(--el-fill-color-light);
  display: block;
  flex: none;
}
.thumb-none {
  line-height: 40px;
  text-align: center;
  color: var(--el-text-color-placeholder);
}
.product-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.product-sku {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
