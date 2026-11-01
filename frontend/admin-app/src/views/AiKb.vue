<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminKbChunks, adminKbDocs, adminKbRebuild, adminKbUpload } from '../api'

/**
 * AI 知识库（Day 120）：查看文档/切片、重建索引、上传新文档。
 * 切片与向量都在 Python 服务里，这里只做管理入口。
 */
const docs = ref<Array<{ source: string; chunks: number; indexedAt: string }>>([])
const loading = ref(false)
const chunksVisible = ref(false)
const chunks = ref<Array<{ id: number; heading: string; content: string }>>([])
const chunksTitle = ref('')
const uploadVisible = ref(false)
const form = reactive({ name: '', content: '' })

async function load() {
  loading.value = true
  try {
    docs.value = (await adminKbDocs()).data.items || []
  } finally {
    loading.value = false
  }
}

async function openChunks(source: string) {
  chunks.value = (await adminKbChunks(source)).data.items || []
  chunksTitle.value = source
  chunksVisible.value = true
}

async function rebuild() {
  await ElMessageBox.confirm('重新切分并向量化全部文档？', '重建索引', { type: 'warning' })
  const j = await adminKbRebuild()
  ElMessage.success(`重建完成：${j.data.files} 个文件 / ${j.data.chunks} 个切片`)
  load()
}

async function submitUpload() {
  if (!form.name.trim() || !form.content.trim()) {
    ElMessage.warning('文件名和内容都要填')
    return
  }
  const j = await adminKbUpload(form.name.trim(), form.content)
  ElMessage.success(`已保存 ${j.data.saved}，重建 ${j.data.chunks} 个切片`)
  uploadVisible.value = false
  form.name = ''
  form.content = ''
  load()
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <el-button type="primary" @click="uploadVisible = true">上传文档</el-button>
      <el-button @click="rebuild">重建索引</el-button>
      <span class="hint">索引由 ai-service 维护（Hash/真实 embedding 取决于环境变量）</span>
    </div>

    <el-table :data="docs" border stripe style="margin-top: 12px">
      <el-table-column prop="source" label="文档" min-width="220" />
      <el-table-column prop="chunks" label="切片数" width="100" />
      <el-table-column prop="indexedAt" label="最近索引时间" width="200" />
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button link type="primary" @click="openChunks(row.source)">查看切片</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty description="还没有知识文档" /></template>
    </el-table>

    <el-dialog v-model="chunksVisible" :title="`切片 · ${chunksTitle}`" width="720px">
      <el-scrollbar max-height="60vh">
        <div v-for="c in chunks" :key="c.id" class="chunk">
          <div class="chunk-head">{{ c.heading || '（无小节）' }} · #{{ c.id }}</div>
          <div class="chunk-body">{{ c.content }}</div>
        </div>
      </el-scrollbar>
    </el-dialog>

    <el-dialog v-model="uploadVisible" title="上传知识文档" width="680px">
      <el-form label-width="80px">
        <el-form-item label="文件名">
          <el-input v-model="form.name" placeholder="如 06-after-sale.md" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="10" placeholder="Markdown；## 二级标题会作为小节名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" @click="submitUpload">保存并重建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.chunk {
  padding: 10px 0;
  border-bottom: 1px dashed var(--el-border-color);
}
.chunk-head {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.chunk-body {
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}
</style>
