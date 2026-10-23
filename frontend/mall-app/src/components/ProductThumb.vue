<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'

/**
 * 商品图（Day 57 · 视觉重做）。
 *
 * <p>★★ 为什么必须有这个组件：种子数据里的图是 `https://oss.mallx.local/...`，
 * 这个域名解析不了 ⇒ 原来的裸 `<img>` 会渲染成一张白框。
 * 一屏 5 张白框，页面看起来就像「没做完」——这是这一轮重做要解决的第一件事。
 *
 * <p>兜底规则：
 * <ul>
 *   <li>有 src 且加载成功 → 正常显示；</li>
 *   <li>没 src / 加载失败 → <b>确定性渐变</b>（由 seed 决定，同一商品每次同一色）+ 名称首字。</li>
 * </ul>
 * 「确定性」很关键：随机色会让每次刷新都变，用户会以为图在闪。
 */
const props = withDefaults(
  defineProps<{
    src?: string | null
    name?: string
    /** 用来选渐变的稳定种子（传商品 id）；不传则用名称 */
    seed?: number | string
    /** 图片的裁切方式：cover（默认，卡片用）/ contain（品牌 logo 用） */
    fit?: 'cover' | 'contain'
  }>(),
  { src: '', name: '', seed: '', fit: 'cover' },
)

const failed = ref(false)

/**
 * ★ 兜底超时：图片指向的域名可能「解析失败要等好几秒」，这段时间 <img> 既不 load 也不 error，
 * 卡片里就是一个空框。1.2 秒还没加载出来就按失败处理 —— 宁可显示占位，也不要白框。
 * ★ 不用 @load 之外的手段判断：onload 触发即清掉定时器，正常图完全不受影响。
 */
let timer: ReturnType<typeof setTimeout> | null = null
if (props.src) {
  timer = setTimeout(() => {
    if (!failed.value) failed.value = true
  }, 1200)
}

function onLoad() {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}
onUnmounted(() => {
  if (timer) clearTimeout(timer)
})

/** 四组暖灰 / 暖棕渐变 —— 与纸感底色同一族，不抢商品 */
const PALETTES: Array<[string, string]> = [
  ['#efe7dc', '#d8c4ad'],
  ['#ece9e3', '#c9c2b6'],
  ['#f1e7e0', '#dbb6a2'],
  ['#e9e9e2', '#c6c8ba'],
]

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h
}

const palette = computed(() => {
  const key = String(props.seed ?? '') || props.name || 'mallx'
  return PALETTES[hash(key) % PALETTES.length]
})

const fallbackStyle = computed(() => ({
  background: `linear-gradient(135deg, ${palette.value[0]} 0%, ${palette.value[1]} 100%)`,
}))

const initial = computed(() => (props.name || 'M').trim().charAt(0).toUpperCase())

const showImage = computed(() => !!props.src && !failed.value)
</script>

<template>
  <div class="thumb" :class="{ 'thumb--contain': fit === 'contain' }">
    <img
      v-if="showImage"
      :src="src || ''"
      :alt="name"
      loading="lazy"
      decoding="async"
      @load="onLoad"
      @error="failed = true"
    />
    <div v-else class="fallback" :style="fallbackStyle">
      <span class="initial">{{ initial }}</span>
    </div>
  </div>
</template>

<style scoped>
.thumb {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--mx-line-soft);
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.thumb--contain img {
  object-fit: contain;
  padding: 8px;
}
/* ★ 绝对定位铺满：父级是靠 aspect-ratio 撑高的，子级 100% 高度在部分嵌套下算不出来，
   会退化成「内容在左上角」——首版截图就踩到了。 */
.fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.initial {
  font-family: Georgia, 'Times New Roman', 'Songti SC', serif;
  font-size: 34px;
  font-weight: 500;
  color: rgba(25, 23, 20, 0.42);
  letter-spacing: 0.02em;
  user-select: none;
}
</style>
