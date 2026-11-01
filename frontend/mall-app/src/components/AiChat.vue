<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { aiChat } from '../api'
import { useAuthStore } from '../stores/auth'

/**
 * AI 客服挂件（Day 59）。
 *
 * <p>★★ 它只是一个<b>前端壳</b>：真正的安全边界在后端 ——
 * 工具不带 userId 入参、写操作一个都没有；前端把 history 传上去也会被服务端过滤掉 system。
 *
 * <p>★ 登录态只影响「能不能查订单」：游客也能问商品，后端会返回「请先登录」。
 *
 * <p>★★ 可拖动（Day 60）：按钮位置存在 localStorage，刷新后保持；
 * 拖过 4px 才算「移动」，否则仍按点击处理 —— 否则用户永远点不开面板。
 */
interface Msg {
  role: 'user' | 'assistant'
  content: string
  tools?: string[]
  mock?: boolean
  sources?: Array<{ source: string; heading?: string; snippet?: string }>
  elapsedMs?: number
  conversationId?: number | null
  tokens?: number
}

const auth = useAuthStore()
const open = ref(false)
const input = ref('')
const sending = ref(false)
const listRef = ref<HTMLElement | null>(null)
const fabRef = ref<HTMLElement | null>(null)

// ---------------- 拖动 / 位置 ----------------
const FAB_KEY = 'mall_ai_fab_pos'
const FAB_SIZE = 46
const PANEL_W = 360
const PANEL_H = 520
const MARGIN = 8

/** null = 默认停右下角（CSS 负责）；拖动过之后才有绝对坐标 */
const pos = ref<{ x: number; y: number } | null>(null)

const fabStyle = computed(() => (pos.value ? { left: `${pos.value.x}px`, top: `${pos.value.y}px` } : {}))

/** 面板跟随按钮：优先放上方；上方不够就放下方；左右贴边钳制 */
const panelStyle = computed(() => {
  if (!pos.value) return {}
  const vw = window.innerWidth
  const vh = window.innerHeight
  const left = clamp(pos.value.x + FAB_SIZE - PANEL_W, 12, Math.max(12, vw - PANEL_W - 12))
  let top = pos.value.y - PANEL_H - 12
  if (top < 12) {
    top = clamp(pos.value.y + FAB_SIZE + 12, 12, Math.max(12, vh - PANEL_H - 12))
  }
  return { left: `${left}px`, top: `${top}px`, right: 'auto', bottom: 'auto' }
})

function clamp(v: number, min: number, max: number) {
  return Math.min(Math.max(v, min), Math.max(min, max))
}

function loadPos() {
  try {
    const raw = localStorage.getItem(FAB_KEY)
    if (!raw) return
    const p = JSON.parse(raw) as { x: number; y: number }
    if (typeof p.x === 'number' && typeof p.y === 'number') {
      pos.value = {
        x: clamp(p.x, MARGIN, window.innerWidth - FAB_SIZE - MARGIN),
        y: clamp(p.y, MARGIN, window.innerHeight - FAB_SIZE - MARGIN),
      }
    }
  } catch {
    /* 坏数据就当没存过 */
  }
}

let dragging = false
let moved = false
let startX = 0
let startY = 0
let originX = 0
let originY = 0

function onPointerDown(e: PointerEvent) {
  const el = fabRef.value
  if (!el) return
  const r = el.getBoundingClientRect()
  dragging = true
  moved = false
  startX = e.clientX
  startY = e.clientY
  originX = r.left
  originY = r.top
  try {
    el.setPointerCapture(e.pointerId)
  } catch {
    /* 合成事件没有真实 pointerId 时会抛，忽略 */
  }
}

function onPointerMove(e: PointerEvent) {
  if (!dragging) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (!moved && Math.hypot(dx, dy) < 4) return
  moved = true
  pos.value = {
    x: clamp(originX + dx, MARGIN, window.innerWidth - FAB_SIZE - MARGIN),
    y: clamp(originY + dy, MARGIN, window.innerHeight - FAB_SIZE - MARGIN),
  }
}

function onPointerUp(e: PointerEvent) {
  if (!dragging) return
  dragging = false
  try {
    fabRef.value?.releasePointerCapture(e.pointerId)
  } catch {
    /* ignore */
  }
  if (moved) {
    if (pos.value) localStorage.setItem(FAB_KEY, JSON.stringify(pos.value))
  } else {
    toggle()
  }
}

function onResize() {
  if (!pos.value) return
  pos.value = {
    x: clamp(pos.value.x, MARGIN, window.innerWidth - FAB_SIZE - MARGIN),
    y: clamp(pos.value.y, MARGIN, window.innerHeight - FAB_SIZE - MARGIN),
  }
}

const conversationId = ref<number | null>(Number(localStorage.getItem('mallx_ai_conv')) || null)
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
    // Day 79：优先走 SSE 流式；失败自动退回同步接口
    messages.value.push({ role: 'assistant', content: '' })
    const target = messages.value[messages.value.length - 1]
    const streamed = await streamChat(content, history, (delta) => {
      target.content += delta
      scrollToBottom()
    }, (meta) => {
      target.mock = !!meta.mock
      target.tools = meta.tools
      target.sources = meta.sources
      target.elapsedMs = meta.elapsedMs
      if (meta.conversationId) {
        conversationId.value = meta.conversationId
        localStorage.setItem('mallx_ai_conv', String(meta.conversationId))
      }
      target.tokens = meta.tokens
    })
    if (!streamed) {
      messages.value.pop()
      const r = await aiChat(content, history, conversationId.value)
      messages.value.push({
        role: 'assistant',
        content: r.data.reply,
        tools: r.data.tools,
        sources: r.data.sources,
        elapsedMs: r.data.elapsedMs,
        tokens: r.data.tokens,
        mock: r.data.mode === 'mock',
      })
    }
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


/**
 * SSE 流式对话：返回 false 表示"流不可用"（网络/接口错误），调用方退回同步接口。
 * 事件：delta{text} / done{mock,tools} / error{message}
 */
async function streamChat(
  content: string,
  history: { role: string; content: string }[],
  onDelta: (t: string) => void,
  onDone: (meta: { mock?: boolean; tools?: string[]; sources?: Msg['sources']; elapsedMs?: number; conversationId?: number | null; tokens?: number }) => void,
): Promise<boolean> {
  try {
    const res = await fetch('/api/ai/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}),
      },
      body: JSON.stringify({ message: content, history, conversationId: conversationId.value }),
    })
    if (!res.ok || !res.body) return false
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const blocks = buf.split('\n\n')
      buf = blocks.pop() ?? ''
      for (const block of blocks) {
        let event = 'message'
        let data = ''
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) data += line.slice(5).trim()
        }
        if (!data) continue
        const obj = JSON.parse(data) as { text?: string; mock?: boolean; tools?: string[]; sources?: Msg['sources']; elapsedMs?: number; conversationId?: number | null; tokens?: number; message?: string }
        if (event === 'delta' && obj.text) onDelta(obj.text)
        else if (event === 'done') onDone(obj)
        else if (event === 'error') throw new Error(obj.message || 'stream error')
      }
    }
    return true
  } catch {
    return false
  }
}

function clearChat() {
  messages.value = [{ role: 'assistant', content: '你好，我是 MallX 客服小 M。想了解商品、订单还是售后？' }]
  conversationId.value = null
  localStorage.removeItem('mallx_ai_conv')
}

function toggle() {
  open.value = !open.value
  if (open.value) scrollToBottom()
}

onMounted(() => {
  scrollToBottom()
  loadPos()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <!-- 悬浮按钮：可拖动；拖过 4px 才视为移动，否则仍是点击开关 -->
  <button
    ref="fabRef"
    class="fab"
    type="button"
    :class="{ 'fab--open': open, 'fab--free': !!pos }"
    :style="fabStyle"
    title="拖动可移动"
    @pointerdown.prevent="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
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

  <!-- 对话面板：跟随按钮位置（拖到左边就出现在左边） -->
  <div class="panel" :class="{ 'panel--open': open }" :style="panelStyle">
    <header class="panel-head">
      <div>
        <div class="title">小 M</div>
        <div class="subtitle">AI 客服 · 售前导购 / 售后查询</div>
      </div>
      <div class="head-actions">
        <button class="clear-btn" type="button" @click="clearChat">清空</button>
        <span class="dot" />
      </div>
    </header>

    <div ref="listRef" class="msgs">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="`msg--${m.role}`">
        <div class="bubble">{{ m.content }}</div>
        <div v-if="m.mock" class="meta">开发模式（未接大模型）</div>
        <div v-else-if="m.tools && m.tools.length" class="meta">
          查了：{{ m.tools.join(' · ') }}
          <span v-if="m.elapsedMs"> · {{ m.elapsedMs }} ms</span>
          <span v-if="m.tokens"> · {{ m.tokens }} tokens</span>
        </div>
        <div v-if="m.sources && m.sources.length" class="sources">
          <span v-for="(s, si) in m.sources" :key="si" class="source-chip">
            <el-popover
              v-if="s.snippet"
              placement="top"
              :width="280"
              trigger="click"
              :content="s.snippet"
            >
              <template #reference>
                <button type="button" class="source-chip source-chip--clickable">
                  {{ s.source }}<template v-if="s.heading"> · {{ s.heading }}</template>
                </button>
              </template>
            </el-popover>
            <span v-else class="source-chip">
              {{ s.source }}<template v-if="s.heading"> · {{ s.heading }}</template>
            </span>
          </span>
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
.sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.clear-btn {
  border: 1px solid var(--mx-line);
  background: transparent;
  color: var(--mx-ink-2);
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 10px;
  cursor: pointer;
}
.clear-btn:hover {
  color: var(--mx-accent);
  border-color: var(--mx-accent);
}
.source-chip {
  font-size: 11px;
  color: var(--mx-ink-3);
  border: 1px solid var(--mx-line);
  border-radius: 999px;
  padding: 1px 8px;
  background: var(--mx-line-soft);
}
.source-chip--clickable {
  cursor: pointer;
}
.source-chip--clickable:hover {
  border-color: var(--mx-accent);
  color: var(--mx-accent);
}

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
  cursor: grab;
  /* ★ 拖动时不要选中文字、不要触发页面滚动（触屏） */
  touch-action: none;
  user-select: none;
  box-shadow: 0 10px 30px rgba(25, 23, 20, 0.18);
  transition: transform 0.18s var(--mx-ease), background 0.18s var(--mx-ease);
}
.fab:active {
  cursor: grabbing;
}
/* 拖动过之后用 left/top 定位，必须把默认的 right/bottom 让开 */
.fab--free {
  right: auto;
  bottom: auto;
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
