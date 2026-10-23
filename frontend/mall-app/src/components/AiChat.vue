<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { aiChat } from '../api'
import { useAuthStore } from '../stores/auth'

/**
 * AI 客服挂件（Day 59）。
 *
 * <p>★★ 它只是一个<b>前端壳</b>：真正的安全边界在后端 ——
 * 工具不带 userId 入参、写操作一个都没有；前端把 history 传上去也会被服务端过滤掉 system。
 *
 * <p>★ 登录态只影响「能不能查订单」：游客也能问商品，后端会返回「请先登录」。
 */
interface Msg {
  role: 'user' | 'assistant'
  content: string
  tools?: string[]
  mock?: boolean
}

const auth = useAuthStore()
const open = ref(false)
const input = ref('')
const sending = ref(false)
const listRef = ref<HTMLElement | null>(null)

const messages = ref<Msg[]>([
  {
    role: 'assistant',
    content:
      '你好，我是 MallX 客服小 M。\n可以问我：有什么手机推荐 / 我的订单到哪了 / 退款进度。\n' +
      (auth.token ? '' : '（登录后可以查订单与售后）'),
  },
])

const quick = ['有什么手机推荐', '我的订单到哪了', '退款到哪一步了']

function scrollToBottom() {
  nextTick(() => {
    const el = listRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function send(text?: string) {
  const content = (text ?? input.value).trim()
  if (!content || sending.value) return
  open.value = true
  input.value = ''
  messages.value.push({ role: 'user', content })
  scrollToBottom()

  sending.value = true
  try {
    // ★ 只回传最近 6 轮，且只回传 user/assistant（服务端还会再过滤一次）
    const history = messages.value
      .slice(0, -1)
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.content }))
    const r = await aiChat(content, history)
    messages.value.push({
      role: 'assistant',
      content: r.data.reply,
      tools: r.data.tools,
      mock: r.data.mode === 'mock',
    })
  } catch {
    // 拦截器已提示；这里补一条可见的失败态，避免输入区看起来"没反应"
    messages.value.push({
      role: 'assistant',
      content: '刚才没连上，稍后再试一次；着急可以直接去「个人中心」看订单。',
    })
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function toggle() {
  open.value = !open.value
  if (open.value) scrollToBottom()
}

onMounted(scrollToBottom)
</script>

<template>
  <!-- 悬浮按钮 -->
  <button class="fab" type="button" :class="{ 'fab--open': open }" @click="toggle">
    <svg v-if="!open" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
      stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12a8 8 0 0 1-8 8H7l-4 3v-6.5A8 8 0 1 1 21 12Z" />
      <path d="M8.5 11h7M8.5 14.5h4.5" />
    </svg>
    <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
    <span v-if="!open" class="fab-label">客服</span>
  </button>

  <!-- 对话面板 -->
  <div class="panel" :class="{ 'panel--open': open }">
    <header class="panel-head">
      <div>
        <div class="title">小 M</div>
        <div class="subtitle">AI 客服 · 售前导购 / 售后查询</div>
      </div>
      <span class="dot" />
    </header>

    <div ref="listRef" class="msgs">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="`msg--${m.role}`">
        <div class="bubble">{{ m.content }}</div>
        <div v-if="m.mock" class="meta">开发模式（未接大模型）</div>
        <div v-else-if="m.tools && m.tools.length" class="meta">
          查了：{{ m.tools.join(' · ') }}
        </div>
      </div>
      <div v-if="sending" class="msg msg--assistant">
        <div class="bubble typing"><span /><span /><span /></div>
      </div>
    </div>

    <div v-if="messages.length <= 1" class="quick">
      <button v-for="q in quick" :key="q" type="button" class="chip" @click="send(q)">{{ q }}</button>
    </div>

    <div class="composer">
      <input
        v-model="input"
        class="input"
        maxlength="500"
        placeholder="问商品、订单或售后…"
        @keyup.enter="send()"
      />
      <button class="send" type="button" :disabled="sending || !input.trim()" @click="send()">
        发送
      </button>
    </div>
  </div>
</template>

<style scoped>
.fab {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 120;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 46px;
  padding: 0 18px;
  border: none;
  border-radius: 999px;
  background: var(--mx-ink);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  box-shadow: 0 10px 30px rgba(25, 23, 20, 0.18);
  transition: transform 0.18s var(--mx-ease), background 0.18s var(--mx-ease);
}
.fab:hover {
  background: var(--mx-deep-2);
  transform: translateY(-1px);
}
.fab--open {
  width: 46px;
  padding: 0;
  justify-content: center;
}
.fab-label {
  letter-spacing: 0.04em;
}

.panel {
  position: fixed;
  right: 28px;
  bottom: 86px;
  z-index: 120;
  width: 360px;
  max-width: calc(100vw - 40px);
  height: 520px;
  max-height: calc(100vh - 120px);
  display: none;
  flex-direction: column;
  background: var(--mx-surface);
  border: 1px solid var(--mx-line);
  border-radius: 14px;
  box-shadow: 0 24px 60px rgba(25, 23, 20, 0.16);
  overflow: hidden;
}
.panel--open {
  display: flex;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid var(--mx-line-soft);
}
.title {
  font-size: 15px;
  font-weight: 600;
  color: var(--mx-ink);
}
.subtitle {
  margin-top: 2px;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--mx-ink-3);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2ea44f;
}

.msgs {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.msg {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 86%;
}
.msg--user {
  align-self: flex-end;
  align-items: flex-end;
}
.msg--assistant {
  align-self: flex-start;
}
.bubble {
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg--assistant .bubble {
  background: var(--mx-line-soft);
  color: var(--mx-ink);
}
.msg--user .bubble {
  background: var(--mx-ink);
  color: #fff;
}
.meta {
  font-size: 10px;
  color: var(--mx-ink-3);
  padding: 0 4px;
}

.typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}
.typing span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--mx-ink-3);
  animation: blink 1.2s infinite ease-in-out;
}
.typing span:nth-child(2) {
  animation-delay: 0.15s;
}
.typing span:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes blink {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}

.quick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 12px;
}
.chip {
  border: 1px solid var(--mx-line);
  background: var(--mx-surface);
  color: var(--mx-ink-2);
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  cursor: pointer;
}
.chip:hover {
  border-color: var(--mx-ink-3);
  color: var(--mx-ink);
}

.composer {
  display: flex;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--mx-line-soft);
}
.input {
  flex: 1;
  min-width: 0;
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--mx-line);
  border-radius: 8px;
  font-size: 13px;
  color: var(--mx-ink);
  outline: none;
}
.input:focus {
  border-color: var(--mx-ink-3);
}
.send {
  flex: none;
  height: 38px;
  padding: 0 16px;
  border: none;
  border-radius: 8px;
  background: var(--mx-accent);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}
.send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 520px) {
  .panel {
    right: 12px;
    left: 12px;
    width: auto;
    bottom: 78px;
  }
  .fab {
    right: 16px;
    bottom: 16px;
  }
}
</style>
