<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  cartList,
  cartRemove,
  cartUpdateQuantity,
  cartUpdateSelected,
} from '../api'
import type { CartItemVO } from '../types/api'
import { useCartStore } from '../stores/cart'

const router = useRouter()
const cartStore = useCartStore()

const items = ref<CartItemVO[]>([])
const selectedAmount = ref(0)
const selectedQuantity = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const j = await cartList()
    items.value = j.data.items || []
    selectedAmount.value = Number(j.data.selectedAmount || 0)
    selectedQuantity.value = Number(j.data.selectedQuantity || 0)
    cartStore.refresh()
  } finally {
    loading.value = false
  }
}

async function changeQuantity(it: CartItemVO, qty: number) {
  if (qty < 1) return
  await cartUpdateQuantity(it.id, qty)
  load()
}

async function toggleSelected(it: CartItemVO, val: boolean) {
  await cartUpdateSelected(it.id, val)
  load()
}

async function remove(it: CartItemVO) {
  await ElMessageBox.confirm(`确定删除「${it.productName}」？`, '删除购物车项', {
    type: 'warning',
  })
  await cartRemove(it.id)
  ElMessage.success('已删除')
  load()
}

/** ★ 失效项不参与结算（服务端也不计入 selectedAmount），这里只置灰 + 禁止勾选 */
function canSelect(it: CartItemVO) {
  return !it.invalid
}

/** 单价/小计统一两位小数 —— 「¥6499」与「¥6499.00」混着显示会显得没整理过 */
function fmt(v: number | string | null | undefined) {
  return Number(v ?? 0).toFixed(2)
}

/** ★ 合计拆成「整数 + 小数」：商城的合计金额都是整数大、小数小（与商品卡同一套语言） */
const totalParts = computed(() => {
  const s = Number(selectedAmount.value ?? 0).toFixed(2)
  const i = s.indexOf('.')
  return { int: s.slice(0, i), dec: s.slice(i) }
})

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="cart-wrap">
    <h2 class="page-title">我的购物车</h2>
    <p v-if="items.length" class="page-sub">
      共 {{ items.length }} 件商品，已选 {{ selectedQuantity }} 件
    </p>

    <el-empty v-if="!loading && items.length === 0" description="购物车还是空的，去挑点东西吧">
      <el-button type="primary" @click="router.push('/')">去逛逛</el-button>
    </el-empty>

    <template v-else>
      <!-- ⚠️ 改造前这里是 el-table —— 表格是「后台管理」的长相。
           商城的购物车是【商品行】：缩略图 + 名称 + 单价 + 数量 + 小计，
           一行一个像卡片，而不是数据库视图。 -->
      <div class="head-row">
        <span class="col-check" />
        <span class="col-goods">商品信息</span>
        <span class="col-price">单价</span>
        <span class="col-qty">数量</span>
        <span class="col-sub">小计</span>
        <span class="col-op">操作</span>
      </div>

      <div v-for="it in items" :key="it.id" class="row" :class="{ invalid: it.invalid }">
        <span class="col-check">
          <el-checkbox
            :model-value="it.selected && !it.invalid"
            :disabled="!canSelect(it)"
            @change="(v: boolean) => toggleSelected(it, v)"
          />
        </span>

        <div class="col-goods goods">
          <img :src="it.image" class="pic" alt="" />
          <div class="goods-meta">
            <div class="gname">{{ it.productName }}</div>
            <div class="sku">{{ it.skuName }}</div>
            <!-- ★ 失效原因直接写在这一行里（而不是只置灰）：
                 用户要一眼知道「为什么这件不能买了」 -->
            <div v-if="it.invalid" class="reason">{{ it.invalidReason }}</div>
          </div>
        </div>

        <span class="col-price muted">¥{{ fmt(it.price) }}</span>

        <span class="col-qty">
          <el-input-number
            :model-value="it.quantity"
            :min="1"
            :max="it.availableStock"
            size="small"
            :disabled="it.invalid"
            @change="(v: number) => changeQuantity(it, v)"
          />
        </span>

        <span class="col-sub sub">¥{{ fmt(it.subtotal) }}</span>

        <span class="col-op">
          <el-button link type="danger" @click="remove(it)">删除</el-button>
        </span>
      </div>

      <!-- ★ 吸底结算栏：购物车是「边看边调」的页面，合计要一直看得见；
           改造前它跟在表格后面，往下滑几屏就找不到了。 -->
      <div class="bar">
        <div class="bar-inner">
          <span class="bar-label">合计（不含运费）</span>
          <span class="amount">
            <span class="sym">¥</span>
            <span class="int">{{ totalParts.int }}</span>
            <span class="dec">{{ totalParts.dec }}</span>
          </span>
          <el-button
            type="primary"
            size="large"
            :disabled="selectedQuantity === 0"
            @click="router.push('/checkout')"
          >
            去结算{{ selectedQuantity ? `（${selectedQuantity}）` : '' }}
          </el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cart-wrap {
  max-width: 1200px;
  margin: 0 auto;
  /* 底部留出吸底栏的高度，否则最后一行会被它盖住 */
  padding: 20px 16px 104px;
  min-height: 260px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 600;
}
.page-sub {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* 表头与数据行共用同一套列宽，两者才对得齐 */
.head-row,
.row {
  display: grid;
  grid-template-columns: 48px minmax(240px, 1fr) 110px 150px 120px 80px;
  align-items: center;
  gap: 10px;
}
.head-row {
  padding: 10px 16px;
  background: var(--el-fill-color-light);
  border-radius: var(--brand-radius) var(--brand-radius) 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.row {
  padding: 14px 16px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background 0.15s ease;
}
.row:hover {
  background: var(--el-fill-color-lighter);
}
.row:last-of-type {
  border-bottom: none;
  border-radius: 0 0 var(--brand-radius) var(--brand-radius);
}
.row.invalid {
  opacity: 0.55;
}

.col-price,
.col-sub,
.col-op {
  text-align: center;
}
.muted {
  color: var(--el-text-color-regular);
  font-size: 13px;
}
/* ★ 小计用价格色 + 加粗：一行里最该被看到的就是「这件花了我多少」 */
.sub {
  color: var(--brand-price);
  font-weight: 700;
}

.goods {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
}
.pic {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: var(--brand-radius-sm);
  background: var(--el-fill-color-light);
  flex: none;
}
.goods-meta {
  min-width: 0;
}
.gname {
  font-size: 14px;
  font-weight: 500;
  /* 超长商品名截断，避免把行撑开 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sku {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.reason {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-color-danger);
}

/* ── 吸底结算栏 ── */
.bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 50;
  background: #fff;
  border-top: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.06);
  padding: 12px 0;
}
.bar-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 18px;
}
.bar-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.amount {
  display: flex;
  align-items: baseline;
  color: var(--brand-price);
  font-weight: 700;
}
.amount .sym {
  font-size: 14px;
}
.amount .int {
  font-size: 24px;
  letter-spacing: -0.5px;
}
.amount .dec {
  font-size: 14px;
}

/* 窄屏：把「单价」列藏掉（小计已经说明问题），保证不横向挤压 */
@media (max-width: 980px) {
  .head-row,
  .row {
    grid-template-columns: 40px minmax(160px, 1fr) 130px 110px 70px;
  }
  .col-price {
    display: none;
  }
}
</style>
