<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  adminCategoryCreate,
  adminCategoryDelete,
  adminCategoryTree,
  adminCategoryUpdate,
} from '../api'
import { useAuthStore } from '../stores/auth'
import { confirmAction } from '../utils/confirm'
import type { CategoryVO } from '../types/api'

/**
 * 分类管理（Day 54）—— 后端 Day 18 就有接口，界面一直缺着。
 *
 * <p>★★ 三条业务规则<b>都在后端 Service 里守</b>，这里的每一条提示都只是「提前说清楚」：
 * <ol>
 *   <li>只允许两级：新增子分类时，父分类自己必须是顶级（否则后端 400）；</li>
 *   <li>改 parentId 不能成环 ⇒ 本页<b>不开放</b>改层级：DTO 约定 parentId=null 一律
 *       「不动」，想换层级只能删了重建；</li>
 *   <li>删除三重校验：有子分类 → 拒；有商品引用（★ 含已软删商品）→ 拒。所以「删除」
 *       按钮点了失败是<b>正常业务结果</b>，不是 bug，文案由拦截器给出。</li>
 * </ol>
 */
const auth = useAuthStore()

const rows = ref<CategoryVO[]>([])
const loading = ref(false)

/** 顶级分类（新增子分类时的父选项；也是「只允许两级」的物理体现） */
const topLevel = computed(() => rows.value.filter((c) => !c.parentId))
const childCount = computed(() =>
  rows.value.reduce((n, c) => n + (c.children?.length ?? 0), 0),
)

async function load() {
  loading.value = true
  try {
    rows.value = (await adminCategoryTree()).data
  } finally {
    loading.value = false
  }
}

// ---------------- 新增 ----------------
const createVisible = ref(false)
const createForm = reactive({
  parentId: null as number | null,
  name: '',
  sortOrder: 0,
})

function openCreate(parent?: CategoryVO) {
  createForm.parentId = parent ? parent.id : null
  createForm.name = ''
  createForm.sortOrder = 0
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.name.trim()) {
    ElMessage.warning('分类名称不能为空')
    return
  }
  try {
    await adminCategoryCreate({
      parentId: createForm.parentId,
      name: createForm.name.trim(),
      sortOrder: createForm.sortOrder,
    })
    ElMessage.success(createForm.parentId ? '子分类已创建' : '顶级分类已创建')
    createVisible.value = false
    await load()
  } catch {
    /* 权限不足 / 校验失败：拦截器已提示 */
  }
}

// ---------------- 编辑 ----------------
const editVisible = ref(false)
const editForm = reactive({ id: 0, name: '', sortOrder: 0, hasChildren: false })

function openEdit(row: CategoryVO) {
  editForm.id = row.id
  editForm.name = row.name
  editForm.sortOrder = row.sortOrder ?? 0
  editForm.hasChildren = !!row.children?.length
  editVisible.value = true
}

async function submitEdit() {
  if (!editForm.name.trim()) {
    ElMessage.warning('分类名称不能为空')
    return
  }
  try {
    // ★ 只发 name / sortOrder：parentId 这条路径本页不开放（见文件头第 2 条）
    await adminCategoryUpdate(editForm.id, {
      name: editForm.name.trim(),
      sortOrder: editForm.sortOrder,
    })
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch {
    /* 拦截器已提示 */
  }
}

// ---------------- 删除 ----------------
async function remove(row: CategoryVO) {
  const ok = await confirmAction(
    `确定删除分类「${row.name}」？\n分类表没有软删，这是【物理删除】；` +
      '有子分类或有商品引用时后端会拒绝。',
    { title: '删除分类', confirmButtonText: '删除', type: 'error' },
  )
  if (!ok) return
  try {
    await adminCategoryDelete(row.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 有子分类 / 有商品引用 / 无权限 —— 拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="bar">
      <span class="stat">
        共 <b>{{ topLevel.length }}</b> 个顶级分类、<b>{{ childCount }}</b> 个子分类
      </span>
      <el-button v-if="auth.hasPerm('category:create')" type="primary" @click="openCreate()">
        新建顶级分类
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="rows"
      row-key="id"
      :tree-props="{ children: 'children' }"
      default-expand-all
      border
      stripe
      style="margin-top: 12px"
    >
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="分类名称" min-width="220" />
      <el-table-column prop="sortOrder" label="排序" width="90" align="center" />
      <el-table-column label="层级" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.parentId ? 'info' : 'success'">
            {{ row.parentId ? '二级' : '顶级' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="子分类数" width="100" align="center">
        <template #default="{ row }">{{ row.children?.length ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <!-- ★ 只有顶级分类能加子分类：这就是「只允许两级」在界面上的样子 -->
          <el-button
            v-if="!row.parentId && auth.hasPerm('category:create')"
            link
            type="primary"
            @click="openCreate(row)"
          >
            加子分类
          </el-button>
          <el-button v-if="auth.hasPerm('category:update')" link type="primary" @click="openEdit(row)">
            编辑
          </el-button>
          <el-button v-if="auth.hasPerm('category:delete')" link type="danger" @click="remove(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="还没有分类">
          <el-button v-if="auth.hasPerm('category:create')" type="primary" @click="openCreate()">
            新建第一个分类
          </el-button>
        </el-empty>
      </template>
    </el-table>

    <!-- 新增 -->
    <el-dialog v-model="createVisible" title="新建分类" width="480px">
      <el-form label-width="90px">
        <el-form-item label="父分类">
          <el-select v-model="createForm.parentId" clearable placeholder="不选 = 顶级分类" style="width: 100%">
            <el-option v-for="c in topLevel" :key="c.id" :value="c.id" :label="c.name" />
          </el-select>
          <div class="hint">只支持两级：父分类必须是顶级分类</div>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" maxlength="100" placeholder="例：手机" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="createForm.sortOrder" :min="0" />
          <span class="hint inline">越小越靠前</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑 -->
    <el-dialog v-model="editVisible" title="编辑分类" width="480px">
      <el-form label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="editForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="editForm.sortOrder" :min="0" />
        </el-form-item>
        <el-form-item v-if="editForm.hasChildren" label="层级">
          <span class="hint">该分类已有子分类，不能再挂到别的分类下面（防止树成环）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.stat {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.stat b {
  color: var(--el-text-color-primary);
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint.inline {
  margin-left: 10px;
}
</style>
