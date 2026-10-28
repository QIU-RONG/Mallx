<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { couponAvailable, couponMy, couponReceive } from '../api'
import type { CouponVO, UserCouponVO } from '../types/api'

/**
 * 我的优惠券（Day 85 视觉重做）。
 *
 * <p>从「Element 卡片 + 红字」改成票券样式：左侧面额区 + 齿孔分割 + 右侧信息/状态，
 * 未使用/已使用/已过期用印章式状态；已失效整张降透明度。
 */
const available = ref<CouponVO[]>([])
const mine = ref<UserCouponVO[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const [a, m] = await Promise.all([
      couponAvailable({ page: 1, size: 50 }),
      couponMy({ page: 1, size: 100 }),
    ])
    available.value = a.data?.records || []
    mine.value = m.data?.records || []
  } finally {
    loading.value = false
  }
}

async function receive(c: CouponVO) {
  await couponReceive(c.id)
  ElMessage.success('领取成功')
  load()
}

function faceValue(c: { discountAmount?: number | null; discountRate?: number | null }) {
  if (c.discountAmount) return { value: Number(c.discountAmount), unit: '元', prefix: '¥' }
  if (c.discountRate) return { value: Number(c.discountRate), unit: '折', prefix: '' }
  return { value: 0, unit: '', prefix: '' }
}

function statusOf(c: UserCouponVO) {
  if (c.expired) return { label: '已过期', kind: 'off' }
  if (c.status === 'USED') return { label: '已使用', kind: 'used' }
  return { label: '未使用', kind: 'ok' }
}

function fmtDate(s?: string) {
  return s ? s.replace('T', ' ').slice(0, 10) : '-'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="wrap">
    <header class="head">
      <div>
        <h1 class="title">我的优惠券</h1>
        <p class="sub">下单时自动可用；已过期 / 已使用的券会变淡</p>
      </div>
      <span class="count">{{ mine.length }} 张</span>
    </header>

    <el-empty v-if="!loading && mine.length === 0" description="还没有券 —— 从下面的「可领取」里领一张" />

    <div v-else class="grid">
      <article
        v-for="c in mine"
        :key="c.id"
        class="ticket"
        :class="{ dim: c.expired || c.status !== 'UNUSED' }"
      >
        <div class="face">
          <div class="amount">
            <span v-if="faceValue(c).prefix" class="prefix">{{ faceValue(c).prefix }}</span>
            <span class="num mx-serif">{{ faceValue(c).value }}</span>
            <span v-if="faceValue(c).unit === '折'" class="unit">{{ faceValue(c).unit }}</span>
          </div>
          <div class="cond">满 {{ Number(c.minAmount || 0).toFixed(0) }} 可用</div>
        </div>
        <div class="body">
          <div class="name">{{ c.couponName }}</div>
          <div class="meta">有效期至 {{ fmtDate(c.endTime) }}</div>
          <span class="stamp" :class="statusOf(c).kind">{{ statusOf(c).label }}</span>
        </div>
      </article>
    </div>

    <section class="available">
      <div class="sec-head">
        <h2 class="sec-title">可领取</h2>
        <span class="sec-sub">先到先得</span>
      </div>

      <el-empty v-if="!loading && available.length === 0" description="暂无可领取的券" />

      <div v-else class="grid">
        <article v-for="c in available" :key="c.id" class="ticket">
          <div class="face">
            <div class="amount">
              <span v-if="faceValue(c).prefix" class="prefix">{{ faceValue(c).prefix }}</span>
              <span class="num mx-serif">{{ faceValue(c).value }}</span>
              <span v-if="faceValue(c).unit === '折'" class="unit">{{ faceValue(c).unit }}</span>
            </div>
            <div class="cond">满 {{ Number(c.minAmount || 0).toFixed(0) }} 可用</div>
          </div>
          <div class="body">
            <div class="name">{{ c.name }}</div>
            <div class="meta">
              剩余 {{ (c.totalCount ?? 0) - (c.receivedCount ?? 0) }} / {{ c.totalCount ?? 0 }}
            </div>
            <button class="claim" type="button" @click="receive(c)">领取</button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.wrap {
  min-height: 320px;
}
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--mx-line);
}
.title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.sub {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--mx-ink-2);
}
.count {
  font-size: 12px;
  color: var(--mx-ink-3);
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 22px;
}

/* ───── 票券 ───── */
.ticket {
  position: relative;
  display: flex;
  min-height: 132px;
  border: 1px solid var(--mx-line);
  border-radius: var(--mx-card-r);
  background: var(--mx-surface);
  /* ★ 不裁剪：齿孔是压在线上的半圆，overflow:hidden 会把它们切掉 */
  overflow: visible;
  transition:
    border-color 0.18s var(--mx-ease),
    transform 0.18s var(--mx-ease);
}
.ticket:hover {
  border-color: var(--mx-ink-3);
  transform: translateY(-2px);
}
.ticket.dim {
  opacity: 0.55;
  filter: grayscale(0.4);
}
.ticket.dim:hover {
  transform: none;
}
.face {
  width: 150px;
  flex: none;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 6px;
  padding: 16px 12px;
  border-right: 1px dashed var(--mx-line);
  background: var(--mx-line-soft);
  /* 左侧面额区自己带圆角，替代外层 overflow:hidden */
  border-radius: calc(var(--mx-card-r) - 1px) 0 0 calc(var(--mx-card-r) - 1px);
}
/* 齿孔：上下两个与页面同色的半圆，压在分割线上 */
.ticket::before,
.ticket::after {
  content: '';
  position: absolute;
  left: 143px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--mx-paper);
  border: 1px solid var(--mx-line);
  z-index: 1;
}
.ticket::before {
  top: -8px;
}
.ticket::after {
  bottom: -8px;
}
.amount {
  display: flex;
  align-items: baseline;
  color: var(--mx-ink);
}
.amount .prefix {
  font-size: 16px;
  margin-right: 2px;
}
.amount .num {
  font-size: 40px;
  line-height: 1;
  letter-spacing: -0.02em;
}
.amount .unit {
  font-size: 16px;
  margin-left: 2px;
}
.cond {
  font-size: 12px;
  color: var(--mx-ink-3);
}
.body {
  flex: 1;
  min-width: 0;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.name {
  font-size: 15px;
  font-weight: 600;
  color: var(--mx-ink);
}
.meta {
  font-size: 12px;
  color: var(--mx-ink-3);
}
.stamp {
  align-self: flex-start;
  margin-top: auto;
  font-size: 11px;
  letter-spacing: 0.08em;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid currentColor;
}
.stamp.ok {
  color: var(--mx-accent);
}
.stamp.used {
  color: var(--mx-ink-3);
}
.stamp.off {
  color: #b3261e;
}
.claim {
  align-self: flex-start;
  margin-top: auto;
  height: 32px;
  padding: 0 16px;
  border: 1px solid var(--mx-ink);
  border-radius: var(--mx-btn-r);
  background: var(--mx-ink);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  transition:
    background 0.18s var(--mx-ease),
    border-color 0.18s var(--mx-ease);
}
.claim:hover {
  background: var(--mx-accent);
  border-color: var(--mx-accent);
}
.available {
  margin-top: 40px;
}
.sec-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-top: 24px;
  border-top: 1px solid var(--mx-line);
}
.sec-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mx-ink);
}
.sec-sub {
  font-size: 12px;
  color: var(--mx-ink-3);
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
