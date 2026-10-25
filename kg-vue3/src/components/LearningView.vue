<!-- 学习提醒：今日到期复习、自评推进间隔（SM-2）。 -->
<template>
  <div class="learn-view">
    <header class="learn-head">
      <div>
        <h2>学习提醒</h2>
        <p>已通过判定的知识会自动进入复习计划，到期后在这里提醒你回看。</p>
      </div>
    </header>

    <div class="learn-stats">
      <div class="u-surface"><strong>{{ stats.total }}</strong><span>在学</span></div>
      <div class="u-surface"><strong>{{ stats.due }}</strong><span>今日到期</span></div>
      <div class="u-surface"><strong>{{ stats.mastered }}</strong><span>已掌握</span></div>
    </div>

    <section class="learn-block">
      <h3>今日待复习</h3>
      <div v-if="loading" class="learn-empty">加载中…</div>
      <div v-else-if="!items.length" class="learn-empty">
        今天没有到期内容。上传并通过判定的知识会自动出现在这里。
      </div>
      <article v-for="item in items" :key="item.id" class="learn-item u-surface">
        <div class="learn-meta">
          <strong>{{ item.title || '未命名知识点' }}</strong>
          <small>第 {{ item.review_count + 1 }} 次 · 当前间隔 {{ item.interval_days }} 天</small>
        </div>
        <div class="learn-grades">
          <button @click="grade(item, 2)">没记住</button>
          <button @click="grade(item, 3)">一般</button>
          <button @click="grade(item, 5)">熟练</button>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { learningAPI } from '@/api'

const stats = ref({ total: 0, due: 0, mastered: 0 })
const items = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const [summary, due] = await Promise.all([learningAPI.stats(), learningAPI.due(50)])
    stats.value = summary
    items.value = due.items || []
  } finally {
    loading.value = false
  }
}

async function grade(item, quality) {
  await learningAPI.review(item.id, quality)
  await load()
}

onMounted(load)
</script>

<style scoped>
.learn-view { padding: 20px 24px; display: flex; flex-direction: column; gap: 18px; }
.learn-head h2 { margin: 0; font-size: var(--fs-lg, 20px); }
.learn-head p { margin: 4px 0 0; color: var(--text-secondary); font-size: var(--fs-sm, 13px); }
.learn-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; max-width: 520px; }
.learn-stats > div { padding: 14px; border-radius: 10px; display: flex; flex-direction: column; gap: 2px; }
.learn-stats strong { font-size: 22px; }
.learn-stats span { color: var(--text-secondary); font-size: 12px; }
.learn-block h3 { margin: 0 0 10px; font-size: var(--fs-md, 15px); }
.learn-item { padding: 14px; border-radius: 10px; display: flex; justify-content: space-between; gap: 16px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.learn-meta { display: flex; flex-direction: column; gap: 4px; }
.learn-meta small { color: var(--text-secondary); font-size: 12px; }
.learn-grades { display: flex; gap: 8px; }
.learn-grades button { border: 1px solid var(--btn-border, var(--border-subtle, #e5e7eb)); background: transparent; border-radius: 999px; padding: 4px 12px; cursor: pointer; font-size: 12px; color: var(--btn-fg, var(--text-secondary)); }
.learn-grades button:first-child { color: var(--mark, #b8362a); }
.learn-empty { padding: 28px; text-align: center; color: var(--text-secondary); font-size: var(--fs-sm, 13px); }
</style>
