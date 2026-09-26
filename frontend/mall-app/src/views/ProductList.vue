<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { brandList, categoryTree, pageProducts } from '../api'
import type { BrandVO, CategoryVO, ProductVO } from '../types/api'

const router = useRouter()

const records = ref<ProductVO[]>([])
const total = ref(0)
const current = ref(1)
const size = ref(12)
const keyword = ref('')
const categoryId = ref<number | undefined>(undefined)
const brandId = ref<number | undefined>(undefined)
const loading = ref(false)

const categories = ref<CategoryVO[]>([])
const brands = ref<BrandVO[]>([])

/** 分类树拍平成「id → 名称」与下拉选项（父+子两级全列出，标出层级） */
const catOptions = ref<{ id: number; label: string }[]>([])

function flatten(nodes: CategoryVO[], prefix = '') {
  for (const n of nodes) {
    catOptions.value.push({ id: n.id, label: prefix + n.name })
    if (n.children?.length) flatten(n.children, prefix + n.name + ' / ')
  }
}

async function load() {
  loading.value = true
  try {
    const j = await pageProducts({
      current: current.value,
      size: size.value,
      categoryId: categoryId.value,
      keyword: keyword.value || undefined,
    })
    let list = j.data.records
    // 后端列表按分类过滤；品牌过滤在 FE1 先前端补刀（页内数据量小），FE2 移到后端
    if (brandId.value != null) list = list.filter((p) => p.brandId === brandId.value)
    records.value = list
    total.value = j.data.total
  } finally {
    loading.value = false
  }
}

function search() {
  current.value = 1
  load()
}

onMounted(async () => {
  load()
  const [c, b] = await Promise.all([categoryTree(), brandList()])
  categories.value = c.data
  catOptions.value = []
  flatten(c.data)
  brands.value = b.data
})
</script>

<template>
  <div class="list-wrap">
    <div class="filter-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索商品名 / 副标题"
        clearable
        style="width: 240px"
        @keyup.enter="search"
        @clear="search"
      />
      <el-select v-model="categoryId" placeholder="全部分类" clearable style="width: 200px" @change="search">
        <el-option v-for="o in catOptions" :key="o.id" :label="o.label" :value="o.id" />
      </el-select>
      <el-select v-model="brandId" placeholder="全部品牌" clearable style="width: 160px" @change="load">
        <el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.id" />
      </el-select>
      <el-button type="primary" @click="search">搜索</el-button>
    </div>

    <div v-loading="loading" class="grid">
      <el-card
        v-for="p in records"
        :key="p.id"
        shadow="hover"
        class="card"
        @click="router.push(`/product/${p.id}`)"
      >
        <img :src="p.mainImage" class="pic" alt="" />
        <div class="name">{{ p.name }}</div>
        <div class="subtitle">{{ p.subtitle }}</div>
        <div class="meta">{{ p.categoryName }} · {{ p.brandName }}</div>
      </el-card>
      <el-empty v-if="!loading && records.length === 0" description="没有匹配的商品" />
    </div>

    <el-pagination
      v-model:current-page="current"
      :page-size="size"
      :total="total"
      layout="prev, pager, next"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.list-wrap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px;
}
.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  min-height: 200px;
}
.card {
  cursor: pointer;
}
.pic {
  width: 100%;
  height: 140px;
  object-fit: cover;
  border-radius: 4px;
  background: #f0f0f0;
}
.name {
  font-weight: 600;
  margin-top: 8px;
}
.subtitle {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  color: #c0c4cc;
  font-size: 12px;
  margin-top: 6px;
}
</style>
