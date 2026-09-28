<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { cartAdd, productDetail } from '../api'
import type { ProductDetailVO } from '../types/api'
import { useCartStore } from '../stores/cart'

const route = useRoute()
const router = useRouter()
const cartStore = useCartStore()
const vo = ref<ProductDetailVO | null>(null)
const mainPic = ref('')
const loading = ref(false)
const chosenSkuId = ref<number | null>(null)
const quantity = ref(1)
const adding = ref(false)

/** 主图 + 图集合并为可迭代字符串数组（模板里不再碰 undefined） */
const pics = ref<string[]>([])

onMounted(async () => {
  loading.value = true
  try {
    const j = await productDetail(route.params.id as string)
    vo.value = j.data
    pics.value = [j.data.mainImage, ...j.data.images].filter((x): x is string => !!x)
    mainPic.value = pics.value[0] || ''
    chosenSkuId.value = j.data.skus[0]?.id ?? null
  } finally {
    loading.value = false
  }
})

function pickMain(url: string) {
  mainPic.value = url
}

async function addToCart() {
  if (chosenSkuId.value == null) {
    ElMessage.warning('请选择规格')
    return
  }
  adding.value = true
  try {
    await cartAdd(chosenSkuId.value, quantity.value)
    cartStore.refresh()
    ElMessage.success('已加入购物车')
  } finally {
    adding.value = false
  }
}
</script>

<template>
  <div v-loading="loading" class="detail-wrap">
    <template v-if="vo">
      <el-breadcrumb style="margin-bottom: 16px">
        <el-breadcrumb-item to="/">首页</el-breadcrumb-item>
        <el-breadcrumb-item>{{ vo.categoryName }}</el-breadcrumb-item>
        <el-breadcrumb-item>{{ vo.name }}</el-breadcrumb-item>
      </el-breadcrumb>

      <div class="main">
        <div class="gallery">
          <img :src="mainPic" class="big" alt="" />
          <div class="thumbs">
            <img
              v-for="url in pics"
              :key="url"
              :src="url"
              class="thumb"
              :class="{ active: url === mainPic }"
              @click="pickMain(url)"
              alt=""
            />
          </div>
        </div>

        <div class="info">
          <h2>{{ vo.name }}</h2>
          <p class="subtitle">{{ vo.subtitle }}</p>
          <el-descriptions :column="1" border style="margin-top: 12px">
            <el-descriptions-item label="分类">{{ vo.categoryName }}</el-descriptions-item>
            <el-descriptions-item label="品牌">{{ vo.brandName }}</el-descriptions-item>
          </el-descriptions>

          <h4 style="margin-top: 16px">选择规格</h4>
          <div class="skus">
            <div
              v-for="s in vo.skus"
              :key="s.id"
              class="sku"
              :class="{ picked: s.id === chosenSkuId }"
              @click="chosenSkuId = s.id"
            >
              <div class="sku-name">{{ s.name || s.skuCode }}</div>
              <div class="sku-price">￥{{ s.price }}</div>
              <div v-if="s.originalPrice" class="sku-orig">￥{{ s.originalPrice }}</div>
            </div>
          </div>

          <div style="margin-top: 20px; display: flex; align-items: center; gap: 12px">
            <span>数量</span>
            <el-input-number v-model="quantity" :min="1" :max="99" size="small" />
            <el-button type="primary" size="large" :loading="adding" @click="addToCart">
              加入购物车
            </el-button>
            <el-button size="large" @click="router.push('/cart')">去购物车结算</el-button>
          </div>
        </div>
      </div>

      <el-card style="margin-top: 24px">
        <template #header>商品详情</template>
        <p style="white-space: pre-wrap">{{ vo.description || '（暂无详情）' }}</p>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.detail-wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
  min-height: 300px;
}
.main {
  display: flex;
  gap: 24px;
}
.gallery {
  width: 380px;
  flex: none;
}
.big {
  width: 380px;
  height: 380px;
  object-fit: cover;
  border-radius: 8px;
  background: #f0f0f0;
}
.thumbs {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.thumb {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border: 2px solid transparent;
  border-radius: 4px;
  cursor: pointer;
}
.thumb.active {
  border-color: #409eff;
}
.subtitle {
  color: #909399;
}
.skus {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.sku {
  border: 2px solid #e4e7ed;
  border-radius: 6px;
  padding: 8px 14px;
  cursor: pointer;
}
.sku.picked {
  border-color: #409eff;
  background: #ecf5ff;
}
.sku-price {
  color: #f56c6c;
  font-weight: 700;
}
.sku-orig {
  color: #c0c4cc;
  text-decoration: line-through;
  font-size: 12px;
}
</style>
