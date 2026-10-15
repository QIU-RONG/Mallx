<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = ref({ username: 'demo', password: 'demo123' })
const loading = ref(false)

async function onSubmit() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const j = await login(form.value.username, form.value.password)
    auth.setAuth(j.data.token, form.value.username, j.data.nickname)
    ElMessage.success('登录成功')
    router.push((route.query.redirect as string) || '/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="never">
      <!-- ★ 品牌区与顶栏同款（渐变方块 + 名称）：登录页是用户见到的第一个界面，
           这儿若没有品牌标识，整个应用就缺了「记忆点」的起点。 -->
      <div class="brand">
        <span class="brand-mark">M</span>
        <span class="brand-name">MallX 商城</span>
      </div>
      <p class="sub">登录后即可加购、下单、查看订单与售后</p>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="用户名">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            size="large"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            size="large"
            placeholder="请输入密码"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit" :loading="loading" @click="onSubmit">
          登 录
        </el-button>
      </el-form>

      <p class="hint">体验账号：demo / demo123（种子用户）</p>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  /* ⚠️ 原来写的是 calc(100vh - 60px) —— 顶栏改成两层（工具条 34 + 主导航 64 = 98）之后，
     那个 60 就成了旧值，页面底部会多出 38px 空白 / 白滚一下。
     ★ 改成用变量算：以后再调顶栏高度，这里自动跟随。 */
  min-height: calc(100vh - var(--brand-utility-h) - var(--brand-header-h));
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: var(--el-fill-color-light);
}
.login-card {
  width: 380px;
  border: 1px solid var(--el-border-color-lighter);
}
.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: var(--brand-radius-sm);
  background: var(--brand-gradient);
  color: #fff;
  font-weight: 800;
  font-size: 17px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-name {
  font-size: 19px;
  font-weight: 700;
  color: var(--brand-color);
  letter-spacing: 0.5px;
}
.sub {
  margin: 8px 0 20px;
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.submit {
  width: 100%;
}
.hint {
  margin-top: 14px;
  font-size: 12px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
