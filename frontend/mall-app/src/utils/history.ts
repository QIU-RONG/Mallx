/**
 * 本地历史记录（Day 69）：搜索历史 + 浏览历史。
 *
 * <p>★ 为什么放 localStorage 而不是数据库：
 * ① 搜索词属于「行为」而不是「交易」，没有对账需求；
 * ② 未登录用户也会有搜索/浏览，落库就得先有匿名 id；
 * ③ 隐私上更干净 —— 用户清一次就真的没了，不需要「注销时删除」。
 *
 * <p>★ 所有读取都 try/catch：坏数据（手改、旧版本格式）按「没有历史」处理，
 * 绝不让 JSON.parse 的异常冒到页面渲染里。
 */

export interface ViewedProduct {
  id: number
  name: string
  image?: string | null
  price?: number | null
  /** 毫秒时间戳，用于按最近顺序展示 */
  at: number
}

const SEARCH_KEY = 'mall_search_history'
const VIEW_KEY = 'mall_view_history'
const SEARCH_MAX = 10
const VIEW_MAX = 20

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function writeJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* 隐私模式/存储满：历史记录不是关键路径，静默失败 */
  }
}

export function getSearchHistory(): string[] {
  const list = readJson<unknown>(SEARCH_KEY, [])
  return Array.isArray(list) ? list.filter((x): x is string => typeof x === 'string').slice(0, SEARCH_MAX) : []
}

/** 去重后置顶；空词忽略 */
export function addSearchHistory(word: string) {
  const w = word.trim()
  if (!w) return
  const next = [w, ...getSearchHistory().filter((x) => x !== w)].slice(0, SEARCH_MAX)
  writeJson(SEARCH_KEY, next)
}

export function clearSearchHistory() {
  writeJson(SEARCH_KEY, [])
}

export function getViewHistory(): ViewedProduct[] {
  const list = readJson<unknown>(VIEW_KEY, [])
  if (!Array.isArray(list)) return []
  return list
    .filter((x): x is ViewedProduct => {
      if (!x || typeof x !== 'object') return false
      const o = x as ViewedProduct
      return typeof o.id === 'number' && typeof o.name === 'string'
    })
    .sort((a, b) => b.at - a.at)
    .slice(0, VIEW_MAX)
}

/** 同一商品只留最近一次；超过 20 条丢最旧的 */
export function addViewHistory(p: Omit<ViewedProduct, 'at'>) {
  const next = [{ ...p, at: Date.now() }, ...getViewHistory().filter((x) => x.id !== p.id)].slice(0, VIEW_MAX)
  writeJson(VIEW_KEY, next)
}

export function clearViewHistory() {
  writeJson(VIEW_KEY, [])
}
