<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  adminPermissionList,
  adminRoleAssignPermissions,
  adminRoleCreate,
  adminRoleDelete,
  adminRoleDetail,
  adminRolePage,
  adminRoleUpdate,
} from '../api'
import { useAuthStore } from '../stores/auth'
import { confirmAction } from '../utils/confirm'
import type { PermissionVO, RoleDetailVO, RoleVO } from '../types/api'

/**
 * 角色与权限（Day 54）。
 *
 * <p>★★ 两条后端护栏，界面上必须<b>提前表达</b>，否则运营会以为「界面坏了」：
 * <ol>
 *   <li>不许删 / 停用 `SUPER_ADMIN` 角色（删=所有人进不来）；</li>
 *   <li>不许<b>减少</b> `SUPER_ADMIN` 的权限（只许增）—— 所以超管已勾选的权限项被禁用，
 *       只能勾新的。后端仍会 400 兜底，这里只是少制造一次失败。</li>
 * </ol>
 *
 * <p>★ 权限字典是<b>只读</b>的：权限码是代码资产，每行都要有一个 `@PreAuthorize` 引用它
 * （见 `AdminPermissionController` 的类注释）—— 所以本页没有「新建权限」。
 */
const auth = useAuthStore()

const rows = ref<RoleVO[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ current: 1, size: 10, keyword: '' })

async function load() {
  loading.value = true
  try {
    const j = await adminRolePage({
      current: query.current,
      size: query.size,
      keyword: query.keyword || undefined,
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

// ---------------- 新建 ----------------
const createVisible = ref(false)
const createForm = reactive({ name: '', code: '', description: '' })

function openCreate() {
  Object.assign(createForm, { name: '', code: '', description: '' })
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.name.trim() || !createForm.code.trim()) {
    ElMessage.warning('角色名与角色码都不能为空')
    return
  }
  try {
    await adminRoleCreate({
      name: createForm.name.trim(),
      code: createForm.code.trim(),
      description: createForm.description.trim() || undefined,
    })
    ElMessage.success('角色已创建')
    createVisible.value = false
    await load()
  } catch {
    /* code 重复 / 无权限：拦截器已提示 */
  }
}

// ---------------- 编辑 ----------------
const editVisible = ref(false)
const editForm = reactive({ id: 0, name: '', code: '', description: '', status: 1 })
const editIsSuper = computed(() => editForm.code === 'SUPER_ADMIN')

function openEdit(row: RoleVO) {
  Object.assign(editForm, {
    id: row.id,
    name: row.name,
    code: row.code,
    description: row.description ?? '',
    status: row.status,
  })
  editVisible.value = true
}

async function submitEdit() {
  if (!editForm.name.trim()) {
    ElMessage.warning('角色名不能为空')
    return
  }
  if (editIsSuper.value && editForm.status === 0) {
    ElMessage.warning('SUPER_ADMIN 不允许停用（停用后所有人都会失去后台权限）')
    return
  }
  try {
    // ★ 只发这三个字段：code 改不了（后端 DTO 里就没有它，改它会让存量 token 里的角色位变孤儿）
    await adminRoleUpdate(editForm.id, {
      name: editForm.name.trim(),
      description: editForm.description.trim(),
      status: editForm.status,
    })
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch {
    /* 护栏 / 无权限：拦截器已提示 */
  }
}

// ---------------- 删除 ----------------
async function remove(row: RoleVO) {
  const ok = await confirmAction(
    `确定删除角色「${row.name}」？\n会一并清理它与管理员、权限的关联；并【不能撤销】。`,
    { title: '删除角色', confirmButtonText: '删除', type: 'error' },
  )
  if (!ok) return
  try {
    await adminRoleDelete(row.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* SUPER_ADMIN / 无权限：拦截器已提示 */
  }
}

// ---------------- 分配权限 ----------------
const assignVisible = ref(false)
const assignRole = ref<RoleDetailVO | null>(null)
const permissions = ref<PermissionVO[]>([])
const checked = ref<number[]>([])
const assignLoading = ref(false)

/** 权限码前缀 → 中文分组名；未登记的按前缀原样显示（不吞数据） */
const PREFIX_LABEL: Record<string, string> = {
  product: '商品',
  category: '分类',
  brand: '品牌',
  order: '订单',
  payment: '支付',
  inventory: '库存',
  review: '评价',
  refund: '售后',
  coupon: '优惠券',
  cart: '购物车',
  address: '地址',
  user: '用户',
  role: '角色',
  permission: '权限',
  admin: '管理员',
  dashboard: '仪表盘',
}

const groups = computed(() => {
  const out: Array<{ prefix: string; label: string; items: PermissionVO[] }> = []
  const index = new Map<string, number>()
  for (const p of permissions.value) {
    const prefix = p.code.split(':')[0] || 'other'
    let at = index.get(prefix)
    if (at == null) {
      at = out.length
      index.set(prefix, at)
      out.push({ prefix, label: PREFIX_LABEL[prefix] ?? prefix, items: [] })
    }
    out[at].items.push(p)
  }
  return out
})

const isSuperRole = computed(() => assignRole.value?.code === 'SUPER_ADMIN')

/**
 * ★ 超管已授予的权限项禁用 —— 这是护栏② 的界面表达（只许增、不许减）。
 * 注意判据用的是<b>打开对话框时</b>的后端集合：本轮新勾的项不在其中，
 * 所以「勾了又取消」在保存前是允许的，不会自锁。
 */
function locked(p: PermissionVO) {
  return isSuperRole.value && !!assignRole.value?.permissionIds.includes(p.id)
}

async function openAssign(row: RoleVO) {
  assignVisible.value = true
  assignLoading.value = true
  assignRole.value = null
  permissions.value = []
  checked.value = []
  try {
    const [detail, dict] = await Promise.all([
      adminRoleDetail(row.id),
      // 没有 permission:list 时这里会 403 —— 对话框显示「加载失败」比空白好排查
      adminPermissionList(),
    ])
    assignRole.value = detail.data
    permissions.value = dict.data
    checked.value = [...detail.data.permissionIds]
  } catch {
    assignVisible.value = false
  } finally {
    assignLoading.value = false
  }
}

async function saveAssign() {
  if (!assignRole.value) return
  try {
    await adminRoleAssignPermissions(assignRole.value.id, checked.value)
    ElMessage.success('权限已保存')
    assignVisible.value = false
    await load()
  } catch {
    /* 超管只许增 / 无权限：拦截器已提示 */
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <div class="bar">
      <el-input
        v-model="query.keyword"
        placeholder="角色名 / 角色码"
        clearable
        style="width: 220px"
        @keyup.enter="search"
        @clear="search"
      />
      <el-button type="primary" @click="search">查询</el-button>
      <span class="spacer" />
      <el-button v-if="auth.hasPerm('role:create')" type="primary" @click="openCreate">
        新建角色
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border stripe style="margin-top: 12px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="角色名" min-width="140" />
      <el-table-column label="角色码" width="180">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.code }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'">
            {{ row.status === 1 ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="createdAt" label="创建时间" width="180" />
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="auth.hasPerm('role:assign-permission')"
            link
            type="primary"
            @click="openAssign(row)"
          >
            分配权限
          </el-button>
          <el-button v-if="auth.hasPerm('role:update')" link type="primary" @click="openEdit(row)">
            编辑
          </el-button>
          <el-button v-if="auth.hasPerm('role:delete')" link type="danger" @click="remove(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="没有匹配的角色" />
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

    <!-- 新建 -->
    <el-dialog v-model="createVisible" title="新建角色" width="520px">
      <el-form label-width="90px">
        <el-form-item label="角色名" required>
          <el-input v-model="createForm.name" maxlength="32" placeholder="例：内容运营" />
        </el-form-item>
        <el-form-item label="角色码" required>
          <el-input v-model="createForm.code" maxlength="32" placeholder="例：CONTENT_OPS" />
          <div class="hint">
            ★ 大写字母开头，只能含大写字母 / 数字 / 下划线；创建后<b>不可修改</b>
            （它以 ROLE_xxx 的形式签进了存量 token）
          </div>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="createForm.description" type="textarea" :rows="2" maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑 -->
    <el-dialog v-model="editVisible" title="编辑角色" width="520px">
      <el-form label-width="90px">
        <el-form-item label="角色码">
          <el-tag type="info">{{ editForm.code }}</el-tag>
          <span class="hint inline">不可修改</span>
        </el-form-item>
        <el-form-item label="角色名" required>
          <el-input v-model="editForm.name" maxlength="32" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="editForm.description" type="textarea" :rows="2" maxlength="255" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="editForm.status" :disabled="editIsSuper">
            <el-radio :value="1">启用</el-radio>
            <el-radio :value="0">停用</el-radio>
          </el-radio-group>
          <div v-if="editIsSuper" class="hint">SUPER_ADMIN 不允许停用（否则谁也进不来）</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分配权限 -->
    <el-dialog
      v-model="assignVisible"
      :title="`分配权限 · ${assignRole?.name ?? ''}`"
      width="720px"
      top="6vh"
    >
      <div v-loading="assignLoading" class="assign">
        <el-alert
          v-if="isSuperRole"
          type="warning"
          :closable="false"
          show-icon
          title="SUPER_ADMIN 的权限只许增不许减：已授予的项被禁用，只能勾选新的。"
        />
        <div v-for="g in groups" :key="g.prefix" class="group">
          <div class="group-title">{{ g.label }}</div>
          <el-checkbox-group v-model="checked">
            <el-checkbox
              v-for="p in g.items"
              :key="p.id"
              :value="p.id"
              :disabled="locked(p) || !auth.hasPerm('role:assign-permission')"
              class="perm"
            >
              <span class="perm-name">{{ p.name }}</span>
              <code class="perm-code">{{ p.code }}</code>
            </el-checkbox>
          </el-checkbox-group>
        </div>
      </div>
      <template #footer>
        <span class="picked">已选 {{ checked.length }} 项</span>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!auth.hasPerm('role:assign-permission')" @click="saveAssign">
          保存
        </el-button>
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
.assign {
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 6px;
}
.group {
  margin-bottom: 14px;
}
.group-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-regular);
  border-left: 3px solid var(--brand-color-light);
  padding-left: 8px;
  margin-bottom: 6px;
}
.perm {
  width: 220px;
  margin-right: 0;
}
.perm-code {
  margin-left: 6px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.picked {
  margin-right: auto;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
