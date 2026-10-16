<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, smsLogin, smsSend } from '../api'
import { BizError } from '../api/http'
import { useAuthStore } from '../stores/auth'
import type { LoginData } from '../types/api'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

/** 登录方式：手机号（默认，Day 52 新增）/ 账号密码（种子用户与既有 e2e 脚本在用） */
const mode = ref<'sms' | 'pwd'>('sms')
const loading = ref(false)

// ==================== 手机号 + 验证码 ====================
const phone = ref('')
const code = ref('')
const countdown = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

/** 手机号合法性：与后端 SmsSendDTO 的 @Pattern 同一条规则（只是提前告诉用户，不是防线） */
const phoneOk = computed(() => /^1[3-9]\d{9}$/.test(phone.value))
const canSend = computed(() => phoneOk.value && countdown.value === 0)

function startCountdown() {
  countdown.value = 60
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0 && timer) {
      clearInterval(timer)
      timer = null
    }
  }, 1000)
}

// ★ SPA 里路由跳走后组件会被销毁，但 setInterval 不会自己停 ——
//   不清掉就是「定时器泄漏」：它继续持有旧的 ref，用户还会看到倒计时在别的页面走完。
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function afterLogin(j: LoginData) {
  // ★ username 在类型上是可选的，但后端两条路径都必然给值（短信路径下它 == 手机号）。
  //   用「返回值 ?? 手机号」兜底：既满足 setAuth(String) 的签名，语义也正确。
  auth.setAuth(j.token, j.username ?? phone.value, j.nickname)
  ElMessage.success('登录成功')
  router.push((route.query.redirect as string) || '/')
}

async function sendCode() {
  if (!canSend.value) return
  const r = await smsSend(phone.value)
  startCountdown()
  if (r.data?.devCode) {
    // ★ 开发模式：本机没有短信服务商，后端把码放进了响应（prod 恒为 null）。
    //   自动填入省掉「去后端日志里翻验证码」这一步。
    code.value = r.data.devCode
    ElMessage.success(`开发模式：验证码 ${r.data.devCode} 已自动填入`)
  } else {
    ElMessage.success('验证码已发送，请查收短信')
  }
}

async function onSmsSubmit() {
  if (!phone.value || !code.value) {
    ElMessage.warning('请输入手机号和验证码')
    return
  }
  loading.value = true
  try {
    const j = await smsLogin(phone.value, code.value)
    afterLogin(j.data)
  } catch (e) {
    // ★★ 这条分支就是本次需求的核心：手机号未注册 ⇒ 带着手机号去注册页。
    //    判据用【业务码 4041】而不是文案 —— 后端 message 改一个字，按文案的跳转
    //    就会静默失效，且 lint / tsc / build 一个都不会报。
    if (e instanceof BizError && e.code === 4041) {
      const redirect = (route.query.redirect as string) || '/'
      router.push({ path: '/register', query: { phone: phone.value, redirect } })
    }
    // 其它错误（验证码错、过期、被限流）http 拦截器已经弹过提示，这里不重复弹。
  } finally {
    loading.value = false
  }
}

// ==================== 账号密码（保留） ====================
const form = ref({ username: 'demo', password: 'demo123' })

async function onPwdSubmit() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const j = await login(form.value.username, form.value.password)
    afterLogin(j.data)
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

      <el-tabs v-model="mode" stretch>
        <el-tab-pane label="手机号登录" name="sms">
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="手机号">
              <el-input
                v-model="phone"
                size="large"
                maxlength="11"
                placeholder="请输入 11 位手机号"
              />
            </el-form-item>
            <el-form-item label="验证码">
              <div class="code-row">
                <el-input
                  v-model="code"
                  size="large"
                  maxlength="6"
                  placeholder="6 位验证码"
                  @keyup.enter="onSmsSubmit"
                />
                <el-button size="large" :disabled="!canSend" @click="sendCode">
                  {{ countdown > 0 ? `${countdown} 秒后重发` : '获取验证码' }}
                </el-button>
              </div>
            </el-form-item>
            <el-button
              type="primary"
              size="large"
              class="submit"
              :loading="loading"
              @click="onSmsSubmit"
            >
              登 录
            </el-button>
          </el-form>
          <p class="hint">未注册的手机号验证通过后会引导你完成注册</p>
        </el-tab-pane>

        <el-tab-pane label="账号密码" name="pwd">
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="用户名">
              <el-input
                v-model="form.username"
                placeholder="请输入用户名"
                size="large"
                @keyup.enter="onPwdSubmit"
              />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="form.password"
                type="password"
                show-password
                size="large"
                placeholder="请输入密码"
                @keyup.enter="onPwdSubmit"
              />
            </el-form-item>
            <el-button
              type="primary"
              size="large"
              class="submit"
              :loading="loading"
              @click="onPwdSubmit"
            >
              登 录
            </el-button>
          </el-form>
          <p class="hint">体验账号：demo / demo123（种子用户）</p>
        </el-tab-pane>
      </el-tabs>
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
  margin: 8px 0 8px;
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
/* 验证码输入 + 获取按钮同一行；输入框吃掉剩余宽度，按钮固定宽度别换行 */
.code-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.code-row .el-input {
  flex: 1;
}
.code-row .el-button {
  white-space: nowrap;
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
