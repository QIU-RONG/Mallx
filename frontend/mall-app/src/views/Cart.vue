<script setup lang="ts">
import { onMounted, ref } from 'vue'
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
    selectedQuantity.value = j.data.selectedQuantity || 0
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

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="cart-wrap">
    <h3>我的购物车</h3>
    <el-empty v-if="!loading && items.length === 0" description="购物车是空的，去逛逛吧">
      <el-button type="primary" @click="router.push('/')">去逛逛</el-button>
    </el-empty>

    <el-table v-else :data="items" style="width: 100%">
      <el-table-column label="选择" width="60">
        <template #default="{ row }">
          <el-checkbox
            :model-value="row.selected && !row.invalid"
            :disabled="!canSelect(row)"
            @change="(v: boolean) => toggleSelected(row, v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="商品" min-width="240">
        <template #default="{ row }">
          <div class="cell-product" :class="{ invalid: row.invalid }">
            <img :src="row.image" class="pic" alt="" />
            <div>
              <div class="name">{{ row.productName }}</div>
              <div class="sku">{{ row.skuName }}</div>
              <div v-if="row.invalid" class="reason">{{ row.invalidReason }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="单价" width="110">
        <template #default="{ row }">￥{{ row.price }}</template>
      </el-table-column>
      <el-table-column label="数量" width="150">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.quantity"
            :min="1"
            :max="row.availableStock"
            size="small"
            :disabled="row.invalid"
            @change="(v: number) => changeQuantity(row, v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="小计" width="110">
        <template #default="{ row }">￥{{ row.subtotal }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="items.length" class="bar">
      <span>已选 {{ selectedQuantity }} 件</span>
      <span class="amount">合计 ￥{{ selectedAmount }}</span>
      <el-button
        type="danger"
        size="large"
        :disabled="selectedQuantity === 0"
        @click="router.push('/checkout')"
      >
        去结算
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.cart-wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
  min-height: 260px;
}
.cell-product {
  display: flex;
  gap: 10px;
  align-items: center;
}
.cell-product.invalid {
  opacity: 0.5;
}
.pic {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 4px;
  background: #f0f0f0;
}
.name {
  font-weight: 600;
}
.sku {
  color: #909399;
  font-size: 12px;
}
.reason {
  color: #f56c6c;
  font-size: 12px;
}
.bar {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-content: flex-end;
  margin-top: 16px;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
}
.amount {
  color: #f56c6c;
  font-size: 20px;
  font-weight: 700;
}
</style>
