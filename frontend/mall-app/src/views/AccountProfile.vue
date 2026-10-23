<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { userMe, userUpdateNickname } from '../api'
import { useAuthStore } from '../stores/auth'
import type { UserVO } from '../types/api'

/**
 * 资料设置（Day 58）。
 *
 * <p>★ 只有昵称可改：用户名/手机号是登录凭据，邮箱与禁用状态由平台管理 ——
 * 界面上把它们标成「不可修改」，比给出一个点了会 400 的输入框诚实。
 *
 * <p>⚠️ 昵称有 `@NotBlank` 与 50 字上限（后端 DTO），前端先拦一次是为了把
 * 「保存成功但页面没变」这种更差的结果排除掉。
 */
const auth = useAuthStore()

const me = ref<UserVO | null>(null)
const nickname = ref('')
const saving = ref(false)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    me.value = (await userMe()).data
    nickname.value = me.value.nickname || ''
  } finally {
    loading.value = false
  }
}

async function save() {
  const v = nickname.value.trim()
  if (!v) {
    ElMessage.warning('昵称不能为空')
    return
  }
  if (v.length > 50) {
    ElMessage.warning('昵称最长 50 个字符')
    return
  }
  saving.value = true
  try {
    await userUpdateNickname(v)
    // ★ 顶栏与个人中心的问候语都读 store —— 不更新它，保存后页面像没生效
    auth.setAuth(auth.token, auth.username, v)
    if (me.value) me.value.nickname = v
    ElMessage.success('昵称已更新')
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="profile">
    <header class="head">
      <h1 class="title">资料设置</h1>
      <p class="sub">手机号与用户名是登录凭据，暂不支持修改</p>
    </header>

    <template v-if="me">
      <dl class="info">
        <div class="row">
          <dt>用户名</dt>
          <dd>{{ me.username }}</dd>
        </div>
        <div class="row">
          <dt>手机号</dt>
          <dd class="mx-serif">{{ me.phone || '-' }}</dd>
        </div>
        <div class="row">
          <dt>邮箱</dt>
          <dd>{{ me.email || '-' }}</dd>
        </div>
        <div class="row">
          <dt>注册时间</dt>
          <dd class="mx-serif">{{ me.createdAt?.replace('T', ' ').slice(0, 16) || '-' }}</dd>
        </div>
        <div class="row">
          <dt>账号状态</dt>
          <dd>{{ me.status === 1 ? '正常' : '已禁用' }}</dd>
        </div>
      </dl>

      <section class="edit">
        <p class="sec-label">修改昵称</p>
        <div class="edit-row">
          <el-input v-model="nickname" maxlength="50" placeholder="昵称" />
          <el-button type="primary" :loading="saving" @click="save">保存</el-button>
        </div>
        <p class="hint">昵称会显示在评价、订单问候与顶栏</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.profile {
  min-height: 320px;
}
.head {
  padding-bottom: 24px;
  border-bottom: 1px solid var(--mx-line);
}
.title {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.sub {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--mx-ink-2);
}

.info {
  margin: 8px 0 0;
}
.row {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid var(--mx-line-soft);
}
.row dt {
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--mx-ink-3);
}
.row dd {
  margin: 0;
  font-size: 14px;
  color: var(--mx-ink);
}

.edit {
  margin-top: 40px;
  max-width: 520px;
}
.sec-label {
  margin: 0 0 12px;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--mx-ink-3);
}
.edit-row {
  display: flex;
  gap: 12px;
}
.edit-row .el-input {
  flex: 1;
}
.hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--mx-ink-3);
}
</style>
