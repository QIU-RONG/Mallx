<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adminLogin } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const form = ref({ username: 'admin', password: 'admin123' })
const loading = ref(false)

async function submit() {
  loading.value = true
  try {
    const j = await adminLogin(form.value.username, form.value.password)
    auth.login(j.data)
    if (auth.perms.length === 0) {
      // 后端只给 type=ADMIN 的 token 发 perms；空 = 这不是管理端身份
      ElMessage.warning('该账号不是管理员身份或没有任何权限码')
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
      <h2>MallX 管理后台</h2>
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
        ★ 管理端与 C 端是两套独立账号体系：这里走 <code>/api/auth/admin/login</code>，
        token 里带 <code>perms</code> 权限码；C 端 token 不能进后台。
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
  margin: 0 0 24px;
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
