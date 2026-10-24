<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminLogin, merchantLogin } from '../api'
import { useAuthStore } from '../stores/auth'

/**
 * 管理端登录（Day 75 增加商户入口）。
 *
 * ★ 两个入口是两套账号表：admins / merchants；
 *   商户 token 同样是 type=ADMIN，但 perms 里带 SHOP_SCOPE_<id>，
 *   菜单会被收成只剩「商品管理」，后端按店铺范围过滤。
 */
const router = useRouter()
const auth = useAuthStore()

const role = ref<'admin' | 'merchant'>('admin')
const form = ref({ username: 'admin', password: 'admin123' })
const loading = ref(false)

function switchRole(r: 'admin' | 'merchant') {
  role.value = r
  form.value =
    r === 'admin' ? { username: 'admin', password: 'admin123' } : { username: 'merchant', password: 'merchant123' }
}

async function submit() {
  loading.value = true
  try {
    const j =
      role.value === 'admin'
        ? await adminLogin(form.value.username, form.value.password)
        : await merchantLogin(form.value.username, form.value.password)
    auth.login(j.data)
    if (auth.perms.length === 0) {
      ElMessage.warning('该账号没有任何权限码')
      return
    }
    ElMessage.success(`欢迎，${j.data.username}`)
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="wrap">
    <el-card class="card">
      <h2>{{ role === 'admin' ? 'MallX 管理后台' : 'MallX 商户后台' }}</h2>

      <div class="tabs">
        <button type="button" class="tab" :class="{ on: role === 'admin' }" @click="switchRole('admin')">
          管理员
        </button>
        <button type="button" class="tab" :class="{ on: role === 'merchant' }" @click="switchRole('merchant')">
          商户
        </button>
      </div>

      <el-form @submit.prevent="submit">
        <el-form-item label="账号">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-button type="primary" class="btn" :loading="loading" @click="submit">登录</el-button>
      </el-form>

      <p class="tip">
        <template v-if="role === 'admin'">
          管理员走 <code>/api/auth/admin/login</code>，token 里带权限码；C 端 token 不能进后台。
        </template>
        <template v-else>
          商户走 <code>/api/auth/merchant/login</code>，登录后只能看到并维护<b>自己店铺</b>的商品。
        </template>
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
}
.card {
  width: 380px;
}
h2 {
  text-align: center;
  margin: 0 0 18px;
}
.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 18px;
  background: var(--el-fill-color-light);
  padding: 4px;
  border-radius: 8px;
}
.tab {
  flex: 1;
  border: none;
  background: transparent;
  padding: 8px 0;
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  cursor: pointer;
}
.tab.on {
  background: #fff;
  color: var(--el-color-primary);
  font-weight: 600;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}
.btn {
  width: 100%;
}
.tip {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
  line-height: 1.7;
}
</style>
