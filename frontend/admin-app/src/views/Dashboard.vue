<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { dashboardOverview, dashboardTrend } from '../api'
import { useAuthStore } from '../stores/auth'
import type { DashboardOverviewVO, TrendPointVO } from '../types/api'

const auth = useAuthStore()

const overview = ref<DashboardOverviewVO | null>(null)
const trend = ref<TrendPointVO[]>([])
const days = ref(7)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const [o, t] = await Promise.all([dashboardOverview(), dashboardTrend(days.value)])
    overview.value = o.data
    trend.value = t.data
  } finally {
    loading.value = false
  }
}

/**
 * ★ 手写 SVG 折线（不引图表库）：把 salesAmount 归一化到 viewBox 坐标。
 * 后端已按「日期骨架 LEFT JOIN」补 0 —— 缺数据的日子不会消失，
 * 所以这里可以直接按数组下标铺 x，不需要再对齐日期。
 */
const W = 640
const H = 200
const PAD = 24

const maxSales = computed(() => Math.max(1, ...trend.value.map((p) => Number(p.salesAmount) || 0)))
const maxOrders = computed(() => Math.max(1, ...trend.value.map((p) => Number(p.orderCount) || 0)))

const points = computed(() =>
  trend.value.map((p, i) => {
    const x =
      trend.value.length === 1
        ? PAD
        : PAD + (i * (W - PAD * 2)) / (trend.value.length - 1)
    const y = H - PAD - ((Number(p.salesAmount) || 0) / maxSales.value) * (H - PAD * 2)
    return { x, y, point: p }
  }),
)

const polyline = computed(() => points.value.map((p) => `${p.x},${p.y}`).join(' '))
const areaPath = computed(() => {
  if (points.value.length === 0) return ''
  const first = points.value[0]
  const last = points.value[points.value.length - 1]
  return `M ${first.x},${H - PAD} L ${polyline.value.split(' ').join(' L ')} L ${last.x},${H - PAD} Z`
})
const barWidth = computed(() =>
  trend.value.length === 0 ? 0 : (W - PAD * 2) / trend.value.length * 0.5,
)

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <!-- ★ 只读汇总也各有一个权限码（dashboard:overview / dashboard:trend） -->
    <template v-if="auth.hasPerm('dashboard:overview')">
      <el-row :gutter="16">
        <el-col :span="6">
          <el-card shadow="never">
            <div class="label">用户总数</div>
            <div class="value">{{ overview?.userCount ?? '-' }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <div class="label">商品数（含下架）</div>
            <div class="value">{{ overview?.productCount ?? '-' }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <div class="label">订单总数（含已取消）</div>
            <div class="value">{{ overview?.orderCount ?? '-' }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <div class="label">销售额（支付流水口径）</div>
            <div class="value money">¥ {{ overview?.salesAmount ?? '-' }}</div>
          </el-card>
        </el-col>
      </el-row>
    </template>
    <el-alert v-else type="warning" show-icon :closable="false" title="当前账号无 dashboard:overview 权限码" />

    <el-card shadow="never" class="chart-card">
      <template #header>
        <div class="head">
          <span>近 {{ days }} 天趋势（订单量 + 销售额）</span>
          <el-select v-model="days" size="small" style="width: 120px" @change="load">
            <el-option :value="7" label="近 7 天" />
            <el-option :value="14" label="近 14 天" />
            <el-option :value="30" label="近 30 天" />
          </el-select>
        </div>
      </template>

      <svg v-if="trend.length" :viewBox="`0 0 ${W} ${H}`" class="chart">
        <!-- 柱状：订单量 -->
        <g>
          <rect
            v-for="p in points"
            :key="'b' + p.point.date"
            :x="p.x - barWidth / 2"
            :y="H - PAD - ((Number(p.point.orderCount) || 0) / maxOrders) * (H - PAD * 2)"
            :width="barWidth"
            :height="((Number(p.point.orderCount) || 0) / maxOrders) * (H - PAD * 2)"
            fill="var(--brand-color-light)"
            opacity="0.45"
          />
        </g>
        <!-- 折线：销售额 -->
        <!-- ★ 颜色改用 CSS 变量：原本写死 #409eff / #79bbff，主色一换这里就成了
             唯一还蓝着的地方（图形不会跟着主题走，光看代码极难发现）。 -->
        <path :d="areaPath" fill="var(--brand-color)" opacity="0.12" />
        <polyline :points="polyline" fill="none" stroke="var(--brand-color)" stroke-width="2" />
        <g>
          <circle
            v-for="p in points"
            :key="'c' + p.point.date"
            :cx="p.x"
            :cy="p.y"
            r="3"
            fill="var(--brand-color)"
          />
        </g>
        <g>
          <text
            v-for="p in points"
            :key="'t' + p.point.date"
            :x="p.x"
            :y="H - 6"
            font-size="10"
            text-anchor="middle"
            fill="var(--el-text-color-secondary)"
          >
            {{ p.point.date.slice(5) }}
          </text>
        </g>
      </svg>
      <el-empty v-else description="暂无趋势数据" />
    </el-card>
  </div>
</template>

<style scoped>
.label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  /* ★ 数字列等宽：销售额跳数时不会左右抖 */
  font-variant-numeric: tabular-nums;
}
/* ★ 金额用 --brand-price（与 C 端同值），而不是随手一个红 */
.value.money {
  color: var(--brand-price);
}
.chart-card {
  margin-top: 16px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.chart {
  width: 100%;
  height: 220px;
}
</style>
