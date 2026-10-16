<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { smsRegister, smsSend } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// ★ 手机号由登录页带过来（它判定「未注册」才转到这儿），但**允许修改**：
//   用户可能输错了号，也可能想换个号注册；做成只读会逼他退回登录页重来一遍。
const phone = ref((route.query.phone as string) || '')
const code = ref('')
const nickname = ref('')
const loading = ref(false)

const countdown = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

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

// ★ 与登录页同理：不清定时器，跳到首页后它还在后台跑
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

async function sendCode() {
  if (!canSend.value) return
  const r = await smsSend(phone.value)
  startCountdown()
  if (r.data?.devCode) {
    // 开发模式：后端把码放进了响应（prod 恒为 null），自动填入
    code.value = r.data.devCode
    ElMessage.success(`开发模式：验证码 ${r.data.devCode} 已自动填入`)
  } else {
    ElMessage.success('验证码已发送，请查收短信')
  }
}

async function submit() {
  if (!phoneOk.value) {
    ElMessage.warning('请输入正确的 11 位手机号')
    return
  }
  if (!code.value) {
    ElMessage.warning('请输入验证码')
    return
  }
  loading.value = true
  try {
    const j = await smsRegister(phone.value, code.value, nickname.value)
    // ★★ 注册即登录：后端直接返回了 token（他刚证明了自己持有这个手机号，
    //    再让他回登录页重输手机号、再等一条验证码，是纯粹的浪费）。
    // ★ 同登录页：username 类型可选，短信注册路径下它 == 手机号，兜底保持语义正确
    auth.setAuth(j.data.token, j.data.username ?? phone.value, j.data.nickname)
    ElMessage.success('注册成功，已自动登录')
    router.push((route.query.redirect as string) || '/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="reg-wrap">
    <el-card class="reg-card" shadow="never">
      <div class="brand">
        <span class="brand-mark">M</span>
        <span class="brand-name">MallX 商城</span>
      </div>
      <!-- ★ 说清「你为什么到了这里」：用户是被登录页转过来的，
           直接甩一个注册表单会让人以为走错了流程。 -->
      <p class="sub">该手机号还未注册，验证后即可完成注册</p>

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
            />
            <el-button size="large" :disabled="!canSend" @click="sendCode">
              {{ countdown > 0 ? `${countdown} 秒后重发` : '获取验证码' }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="昵称（可选）">
          <el-input
            v-model="nickname"
            size="large"
            maxlength="50"
            placeholder="不填则默认「用户 + 手机号后四位」"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit" :loading="loading" @click="submit">
          注册并登录
        </el-button>
      </el-form>

      <p class="hint">
        已有账号？
        <el-button link type="primary" @click="router.push('/login')">返回登录</el-button>
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.reg-wrap {
  min-height: calc(100vh - var(--brand-utility-h) - var(--brand-header-h));
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: var(--el-fill-color-light);
}
.reg-card {
  width: 400px;
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
  margin: 8px 0 18px;
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
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
  margin: 14px 0 0;
  font-size: 12px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
