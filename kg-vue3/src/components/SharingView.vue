<!-- 分享空间：搜索、推荐、热门列表、点赞与上传。 -->
<template>
  <div class="share-view">
    <header class="share-head">
      <div>
        <h2>分享空间</h2>
        <p>看别人整理的知识导图，点赞收藏，也可以上传自己的。</p>
      </div>
      <div class="share-actions">
        <input
          v-model="keyword"
          class="u-input"
          placeholder="搜索标题、摘要或领域…"
          @keyup.enter="doSearch"
        />
        <select v-model="sort" class="u-input" @change="loadList">
          <option value="hot">最热</option>
          <option value="new">最新</option>
        </select>
        <button class="u-btn" @click="showUpload = !showUpload">
          {{ showUpload ? '收起上传' : '上传知识' }}
        </button>
      </div>
    </header>

    <section v-if="showUpload" class="share-upload u-surface">
      <input v-model="form.title" class="u-input" placeholder="标题（必填）" />
      <input v-model="form.domain" class="u-input" placeholder="领域，如 frontend / ai_ml" />
      <input v-model="form.node_id" class="u-input" placeholder="关联图谱节点 ID（可选，填了可直接跳转查看）" />
      <textarea v-model="form.summary" class="u-input" rows="2" placeholder="一句话摘要" />
      <textarea v-model="form.content" class="u-input" rows="5" placeholder="正文（Markdown）" />
      <div class="upload-foot">
        <span v-if="uploadHint" class="hint">{{ uploadHint }}</span>
        <button class="u-btn" :disabled="uploading" @click="submitUpload">
          {{ uploading ? '提交中…' : '提交' }}
        </button>
      </div>
    </section>

    <section v-if="recommend.length" class="share-block">
      <h3>
        为你推荐
        <small v-if="profileDomains.length">偏好：{{ profileDomains.join(' / ') }}</small>
      </h3>
      <div class="card-row">
        <article
          v-for="p in recommend"
          :key="'r' + p.id"
          class="share-card u-surface"
          :class="{ expanded: expandedId === p.id }"
          @click="openPost(p)"
        >
          <header>
            <strong>{{ p.title }}</strong>
            <span class="domain">{{ p.domain }}</span>
          </header>
          <p>{{ p.summary || '（无摘要）' }}</p>
          <p v-if="p.node_count" class="system-line">
            {{ p.node_count }} 个知识点<template v-if="p.link_count"> · {{ p.link_count }} 条关联</template>
          </p>
          <div v-if="p.node_titles && p.node_titles.length" class="system-chips">
            <span v-for="(t, i) in p.node_titles.slice(0, 6)" :key="i">{{ t }}</span>
          </div>
          <div v-if="expandedId === p.id" class="share-detail" @click.stop>
            <p class="detail-body">{{ p.content || p.summary || '（无正文）' }}</p>
            <button class="u-btn" @click="openPost(p)">在图谱中查看整个体系</button>
          </div>
          <footer>
            <span class="reason">{{ p.reason }}</span>
            <span class="card-actions">
              <button
                v-if="p.file_id || p.node_id"
                class="link-btn strong"
                @click.stop="openPost(p)"
              >查看体系</button>
              <button class="link-btn" @click.stop="toggleExpand(p)">
                {{ expandedId === p.id ? '收起' : '全文' }}
              </button>
              <button class="like" :class="{ on: p.liked }" @click.stop="toggleLike(p)">
                ♥ {{ p.like_count }}
              </button>
            </span>
          </footer>
        </article>
      </div>
    </section>

    <section class="share-block">
      <h3>{{ keyword ? `搜索结果（${total}）` : '大家的分享' }}</h3>
      <div v-if="loading" class="share-empty">加载中…</div>
      <div v-else-if="!items.length" class="share-empty">还没有分享，来发第一条。</div>
      <div v-else class="card-grid">
        <article
          v-for="p in items"
          :key="p.id"
          class="share-card u-surface"
          :class="{ expanded: expandedId === p.id }"
          @click="openPost(p)"
        >
          <header>
            <strong>{{ p.title }}</strong>
            <span class="domain">{{ p.domain }}</span>
          </header>
          <p>{{ p.summary || '（无摘要）' }}</p>
          <p v-if="p.node_count" class="system-line">
            {{ p.node_count }} 个知识点<template v-if="p.link_count"> · {{ p.link_count }} 条关联</template>
          </p>
          <div v-if="p.node_titles && p.node_titles.length" class="system-chips">
            <span v-for="(t, i) in p.node_titles.slice(0, 6)" :key="i">{{ t }}</span>
          </div>
          <div v-if="expandedId === p.id" class="share-detail" @click.stop>
            <p class="detail-body">{{ p.content || p.summary || '（无正文）' }}</p>
            <button class="u-btn" @click="openPost(p)">在图谱中查看整个体系</button>
          </div>
          <footer>
            <span class="author">
              {{ p.author }}
              <em v-if="p.status === 'pending'">待判定</em>
            </span>
            <span class="card-actions">
              <button
                v-if="p.file_id || p.node_id"
                class="link-btn strong"
                @click.stop="openPost(p)"
              >查看体系</button>
              <button class="link-btn" @click.stop="toggleExpand(p)">
                {{ expandedId === p.id ? '收起' : '全文' }}
              </button>
              <button
                class="like"
                :class="{ on: p.liked }"
                :disabled="p.status !== 'approved'"
                @click.stop="toggleLike(p)"
              >
                ♥ {{ p.like_count }}
              </button>
            </span>
          </footer>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { shareAPI } from '@/api'

const keyword = ref('')
const sort = ref('hot')
const items = ref([])
const total = ref(0)
const loading = ref(false)
const recommend = ref([])
const profileDomains = ref([])
const showUpload = ref(false)
const uploading = ref(false)
const uploadHint = ref('')
const form = reactive({ title: '', summary: '', content: '', domain: 'general', tags: [], node_id: '' })

const emit = defineEmits(['open-system'])
const expandedId = ref(null)

/** 点击卡片直接进图谱；没有关联知识体系时才就地展开 */
function openPost(post) {
  if (post.file_id || post.node_id) {
    emit('open-system', post)
  } else {
    toggleExpand(post)
  }
}

/** 「全文」按钮：就地展开正文，再点收起 */
function toggleExpand(post) {
  expandedId.value = expandedId.value === post.id ? null : post.id
}

async function loadList() {
  loading.value = true
  try {
    const data = keyword.value
      ? await shareAPI.search(keyword.value, { sort: sort.value })
      : await shareAPI.list({ sort: sort.value })
    items.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadRecommend() {
  const data = await shareAPI.recommend(6)
  recommend.value = data.items || []
  profileDomains.value = data.profile_domains || []
}

function doSearch() {
  loadList()
}

async function toggleLike(post) {
  const data = post.liked ? await shareAPI.unlike(post.id) : await shareAPI.like(post.id)
  post.liked = data.liked
  post.like_count = data.like_count
}

async function submitUpload() {
  if (!form.title.trim()) {
    uploadHint.value = '请先填标题'
    return
  }
  uploading.value = true
  uploadHint.value = ''
  try {
    const post = await shareAPI.create({
      ...form,
      node_id: form.node_id ? Number(form.node_id) : null,
    })
    uploadHint.value = post.status === 'approved'
      ? '已进入分享空间，并加入你的学习计划'
      : '已提交，判定通过后展示'
    form.title = ''
    form.summary = ''
    form.content = ''
    form.node_id = ''
    await Promise.all([loadList(), loadRecommend()])
  } catch (err) {
    uploadHint.value = err.fullMessage || err.message || '提交失败'
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  loadList()
  loadRecommend()
})
</script>

<style scoped>
.share-view { padding: 20px 24px; display: flex; flex-direction: column; gap: 18px; }
.share-head { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.share-head h2 { margin: 0; font-size: var(--fs-lg, 20px); }
.share-head p { margin: 4px 0 0; color: var(--text-secondary); font-size: var(--fs-sm, 13px); }
.share-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.share-actions input { min-width: 220px; }
.share-upload { padding: 14px; display: flex; flex-direction: column; gap: 8px; border-radius: 10px; }
.upload-foot { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.hint { color: var(--text-secondary); font-size: var(--fs-sm, 13px); }
.share-block h3 { margin: 0 0 10px; font-size: var(--fs-md, 15px); }
.share-block h3 small { margin-left: 8px; color: var(--text-secondary); font-weight: 400; }
.card-row { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(240px, 1fr); gap: 12px; overflow-x: auto; padding-bottom: 6px; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.share-card { padding: 14px; border-radius: 10px; display: flex; flex-direction: column; gap: 8px; cursor: pointer; }
.share-card.expanded { border-color: var(--btn-border, #e5e7eb); }
.share-detail { display: flex; flex-direction: column; gap: 8px; padding-top: 10px; border-top: 1px solid var(--btn-border, #e5e7eb); cursor: default; }
.detail-body { min-height: 0 !important; white-space: pre-wrap; }
.detail-actions { display: flex; justify-content: flex-end; }
.detail-muted { color: var(--text-secondary); font-size: 12px; }
.system-line { margin: -2px 0 0; color: var(--text-secondary); font-size: 12px; }
.system-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.system-chips span {
  padding: 1px 6px; border-radius: 4px; font-size: 11px;
  background: var(--btn-hover-bg, rgba(0, 0, 0, 0.05));
  color: var(--btn-fg, var(--text-secondary));
}
.card-actions { display: flex; align-items: center; gap: 6px; }
.link-btn {
  border: 0; background: transparent; padding: 2px 4px; cursor: pointer;
  color: var(--btn-fg, var(--text-secondary)); font-size: 12px;
}
.link-btn:hover { color: var(--btn-strong, var(--text-primary)); }
.link-btn.strong { color: var(--accent, #1677ff); font-weight: 600; }
.share-card header { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.share-card strong { font-size: var(--fs-md, 15px); }
.domain { color: var(--text-secondary); font-size: 12px; }
.share-card p { margin: 0; color: var(--text-secondary); font-size: var(--fs-sm, 13px); line-height: 1.6; min-height: 40px; }
.share-card footer { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.author { color: var(--text-secondary); font-size: 12px; }
.author em { margin-left: 6px; font-style: normal; color: var(--mark, #b8362a); }
.reason { color: var(--text-secondary); font-size: 12px; }
.like { border: 1px solid var(--btn-border, var(--border-subtle, #e5e7eb)); background: transparent; border-radius: 999px; padding: 2px 10px; cursor: pointer; font-size: 12px; color: var(--btn-fg, var(--text-secondary)); }
.like.on { color: var(--mark, #b8362a); border-color: currentColor; }
.like:disabled { opacity: .5; cursor: not-allowed; }
.share-empty { padding: 28px; text-align: center; color: var(--text-secondary); font-size: var(--fs-sm, 13px); }
</style>
