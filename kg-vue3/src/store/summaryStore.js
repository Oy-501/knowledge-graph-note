/**
 * summaryStore.js
 * 图谱总结状态管理
 *
 * 把「网状」的知识图谱总结成：
 *  1) 结构化总结（层级/领域/枢纽/连通簇/学习主线/知识库桥接/孤立点/建议）
 *  2) Mermaid 流程图（把网拉成流，人看得懂、大模型也读得懂）
 *  3) AI 可读摘要（紧凑纯文本，可直接投喂大模型）
 *  4) 导出：Markdown / Word / PPTX / Mermaid / JSON
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { summaryAPI } from '@/api/index'

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export const useSummaryStore = defineStore('summary', () => {
  const summary = ref(null)
  const mermaid = ref('')
  const aiDigest = ref('')
  const generating = ref(false)
  const exporting = ref('')
  const groupBy = ref('level')       // level | domain
  const maxPaths = ref(6)
  const docTitle = ref('知识图谱总结')
  const copied = ref('')

  const overview = computed(() => summary.value?.overview || {})
  const isEmpty = computed(() => summary.value?.empty === true)
  const generatedAt = computed(() => summary.value?.generated_at || '')

  /** 生成总结（三个产物一次拿到） */
  async function generate() {
    generating.value = true
    try {
      const data = await summaryAPI.build({
        groupBy: groupBy.value,
        maxPaths: maxPaths.value,
        title: docTitle.value
      })
      summary.value = data.summary
      mermaid.value = data.mermaid || ''
      aiDigest.value = data.ai_digest || ''
      if (data.empty) {
        ElMessage.warning('图谱还没有知识点，先上传文档再生成总结')
      } else {
        ElMessage.success(
          `总结完成：${overview.value.node_count} 知识点 / ${overview.value.link_count} 关联 / ` +
          `${(summary.value.paths || []).length} 条学习主线`
        )
      }
      return data
    } catch (e) {
      ElMessage.error(`总结生成失败：${e.message}`)
      return null
    } finally {
      generating.value = false
    }
  }

  /** 导出：md | docx | pptx | mermaid | digest | json */
  async function exportAs(fmt) {
    exporting.value = fmt
    try {
      const ext = fmt === 'mermaid' ? 'mmd' : fmt
      const names = {
        md: `${docTitle.value}.md`,
        docx: `${docTitle.value}.docx`,
        pptx: `${docTitle.value}.pptx`,
        mermaid: '知识图谱流程图.mmd',
        digest: '知识图谱AI摘要.md',
        json: `${docTitle.value}.json`
      }
      const blob = await summaryAPI.download(fmt, {
        groupBy: groupBy.value,
        title: docTitle.value
      })
      saveBlob(blob, names[ext] || `${docTitle.value}.${ext}`)
      ElMessage.success(`已导出 ${names[ext] || ext}`)
    } catch (e) {
      ElMessage.error(`导出失败：${e.message}`)
    } finally {
      exporting.value = ''
    }
  }

  async function copy(text, label = '已复制') {
    try {
      await navigator.clipboard.writeText(text || '')
      copied.value = label
      ElMessage.success(label)
      setTimeout(() => { copied.value = '' }, 2000)
    } catch (e) {
      // 剪贴板不可用（非 https / 无权限）时退化为手动选中
      ElMessage.warning('浏览器拒绝了剪贴板访问，请手动全选复制')
    }
  }

  return {
    summary, mermaid, aiDigest, generating, exporting, groupBy, maxPaths, docTitle, copied,
    overview, isEmpty, generatedAt,
    generate, exportAs, copy
  }
})
