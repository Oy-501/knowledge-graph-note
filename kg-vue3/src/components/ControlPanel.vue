<template>
  <!-- 分组管理 -->
  <div class="panel-section">
    <h3>
      📁 分组管理
      <span class="group-view-toggle">
        <button type="button"
          class="view-toggle-btn"
          :class="{ active: groupViewMode === 'tree' }"
          @click="groupViewMode = 'tree'"
          title="树形视图"
        >🌳</button>
        <button type="button"
          class="view-toggle-btn"
          :class="{ active: groupViewMode === 'flat' }"
          @click="groupViewMode = 'flat'"
          title="平铺视图"
        >📋</button>
      </span>
    </h3>
    <!-- 搜索与排序 -->
    <div class="group-toolbar">
      <input
        class="group-search"
        type="text"
        placeholder="搜索分组..."
        :value="groupStore.groupSearch"
        @input="onGroupSearch($event.target.value)"
      />
      <div class="group-sort-btns">
        <button type="button"
          class="sort-btn"
          :class="{ active: groupStore.groupSortBy === 'name' }"
          @click="groupStore.setSortBy('name')"
          title="按名称排序"
        >
          A-Z {{ groupStore.groupSortBy === 'name' ? (groupStore.groupSortAsc ? '↑' : '↓') : '' }}
        </button>
        <button type="button"
          class="sort-btn"
          :class="{ active: groupStore.groupSortBy === 'count' }"
          @click="groupStore.setSortBy('count')"
          title="按节点数排序"
        >
          # {{ groupStore.groupSortBy === 'count' ? (groupStore.groupSortAsc ? '↑' : '↓') : '' }}
        </button>
      </div>
    </div>

    <!-- 树形分组视图 -->
    <div v-if="groupViewMode === 'tree'" class="group-tree">
      <!-- 全部节点 -->
      <div
        class="tree-item tree-root"
        :class="{ active: groupStore.currentGroupId === 'all' }"
        @click="onSwitchGroup('all')"
      >
        <span class="tree-icon">🌐</span>
        <span class="tree-name">全部节点</span>
        <span class="tree-count">{{ graphStore.nodeCount }}</span>
      </div>
      <!-- 递归渲染分组树 -->
      <GroupTreeNode
        v-for="node in groupStore.groupTree"
        :key="node.id"
        :node="node"
        :depth="0"
        :tree-collapsed="groupStore.treeCollapsed"
        :current-group-id="groupStore.currentGroupId"
        @switch-group="onSwitchGroup"
        @toggle-collapse="groupStore.toggleTreeCollapse"
        @toggle-visibility="onToggleVisibility"
        @drag-over="onGroupDragOver"
        @drag-leave="onGroupDragLeave"
        @drop="onGroupDrop"
      />
    </div>

    <!-- 平铺分组标签列表 -->
    <div v-else class="group-tabs">
      <button type="button"
        class="group-tab"
        :class="{ active: groupStore.currentGroupId === 'all' }"
        @click="onSwitchGroup('all')"
      >全部</button>
      <button type="button"
        v-for="g in groupStore.filteredGroups"
        :key="g.id"
        class="group-tab"
        :class="{ active: groupStore.currentGroupId === g.id, hidden: g.visible === false }"
        :style="groupTabStyle(g)"
        @click="onSwitchGroup(g.id)"
        @dragover.prevent="onGroupDragOver($event, g.id)"
        @dragleave="onGroupDragLeave($event)"
        @drop="onGroupDrop($event, g.id)"
        :title="g.description || g.name"
      >
        <span
          class="group-visibility-icon"
          @click.stop="onToggleVisibility(g.id)"
          :title="g.visible === false ? '点击显示' : '点击隐藏'"
        >
          {{ g.visible === false ? '🚫' : '👁' }}
        </span>
        <span class="group-color-dot" :style="{ background: g.color }"></span>
        <span class="group-tab-name">{{ g.name }}</span>
        <span class="group-tab-count">{{ g.count }}</span>
        <button type="button"
          class="group-collapse-btn"
          v-if="g.id !== 'default'"
          @click.stop="groupStore.toggleCollapse(g.id)"
          :title="g.collapsed ? '展开' : '折叠'"
        >{{ g.collapsed ? '▶' : '▼' }}</button>
      </button>
      <button type="button" class="group-tab group-tab-add" @click="onNewGroup" title="新建分组">+</button>
    </div>

    <!-- 隐藏分组提示 -->
    <div v-if="hiddenGroupCount > 0" class="hidden-groups-notice">
      🚫 {{ hiddenGroupCount }} 个分组已隐藏
      <button type="button" class="btn btn-sm" @click="onShowAllGroups">全部显示</button>
    </div>

    <!-- 当前分组操作 -->
    <div class="group-info">
      <span>
        当前：{{ groupStore.currentGroup.name }}（{{
          groupStore.currentGroupId === 'all' ? graphStore.nodeCount : groupStore.currentGroup.count
        }} 个节点）
      </span>
      <span style="color:var(--text-muted);margin-left:8px">全局：{{ graphStore.nodeCount }} 个节点</span>
    </div>

    <!-- 分组描述 -->
    <div v-if="groupStore.currentGroupId !== 'all' && currentGroupDesc" class="group-desc">
      <span class="group-desc-text">{{ currentGroupDesc }}</span>
    </div>

    <!-- 自动归类 -->
    <div style="margin-top:6px">
      <button type="button" class="btn btn-sm btn-primary" @click="onAutoClassify" :disabled="graphStore.isBusy">
        🤖 智能归类
      </button>
      <button type="button" class="btn btn-sm" @click="onPreviewClassify" style="margin-left:4px" :disabled="graphStore.isBusy">
        预览
      </button>
      <p style="font-size:10px;color:var(--text-muted);margin-top:2px">
        基于分组关键词自动匹配未归类节点
      </p>
    </div>

    <!-- 分组统计分布 -->
    <div class="group-distribution" v-if="groupStore.groups.length > 1">
      <div class="gd-header" @click="showGroupDist = !showGroupDist">
        <span>📊 分组分布</span>
        <span class="gd-toggle">{{ showGroupDist ? '▲' : '▼' }}</span>
      </div>
      <div v-if="showGroupDist" class="gd-body">
        <div class="gd-bar-chart">
          <div
            v-for="g in groupStore.visibleGroups"
            :key="g.id"
            class="gd-bar-row"
            :title="`${g.name}: ${g.count} 节点`"
          >
            <span class="gd-bar-label" :style="{ color: g.color }">{{ g.name }}</span>
            <div class="gd-bar-track">
              <div
                class="gd-bar-fill"
                :style="{
                  width: maxCount > 0 ? (g.count / maxCount * 100) + '%' : '0%',
                  background: g.color
                }"
              ></div>
            </div>
            <span class="gd-bar-count">{{ g.count }}</span>
          </div>
        </div>
        <div class="gd-summary">
          <span>{{ groupStore.groups.length }} 个分组</span>
          <span>·</span>
          <span>{{ groupStore.totalNodeCount }} 个节点</span>
          <span v-if="hiddenGroupCount > 0">·</span>
          <span v-if="hiddenGroupCount > 0" style="color:var(--warning)">{{ hiddenGroupCount }} 隐藏</span>
        </div>
      </div>
    </div>

    <div
      v-if="groupStore.currentGroupId !== 'all' && groupStore.currentGroupId !== 'default'"
      class="group-actions"
      style="margin-top:6px"
    >
      <button type="button" class="btn btn-sm" @click="onEditGroup">编辑</button>
      <button type="button" class="btn btn-sm" @click="onRenameGroup">重命名</button>
      <el-color-picker
        class="group-color-pick"
        title="分组颜色"
        :model-value="currentGroupColor"
        :predefine="GROUP_COLORS"
        size="small"
        @change="onGroupColorChange"
      />
      <button type="button" class="btn btn-sm" @click="onMergeGroup">合并到...</button>
      <button type="button" class="btn btn-sm btn-danger" @click="onDeleteGroup">删除分组</button>
    </div>

    <!-- 分组编辑弹窗 -->
    <div v-if="editDialog.visible" class="merge-overlay" @click.self="editDialog.visible = false">
      <div class="merge-dialog" style="max-width:420px">
        <div class="merge-dialog-header">
          <h4>编辑分组「{{ editDialog.name }}」</h4>
          <button type="button" @click="editDialog.visible = false">✕</button>
        </div>
        <div class="merge-dialog-body">
          <div class="edit-field">
            <label>描述</label>
            <textarea
              v-model="editDialog.description"
              rows="2"
              placeholder="分组用途和范围描述..."
              class="edit-textarea"
            ></textarea>
          </div>
          <div class="edit-field">
            <label>关键词（用于智能归类，逗号分隔）</label>
            <input v-model="editDialog.keywordsStr" class="edit-input" placeholder="例如: Vue, 前端, 响应式" />
          </div>
          <div class="edit-field">
            <label>父分组</label>
            <select v-model="editDialog.parentId" class="merge-select">
              <option :value="null">-- 顶层分组 --</option>
              <option
                v-for="g in groupStore.groups"
                :key="g.id"
                :value="g.id"
                :disabled="g.id === groupStore.currentGroupId || isDescendantOf(g.id, groupStore.currentGroupId)"
              >
                {{ getGroupPath(g) }}
              </option>
            </select>
          </div>
        </div>
        <div class="merge-dialog-footer">
          <button type="button" class="btn btn-sm" @click="editDialog.visible = false">取消</button>
          <button type="button" class="btn btn-sm btn-primary" @click="onConfirmEdit">保存</button>
        </div>
      </div>
    </div>

    <!-- 分组合并弹窗 -->
    <div v-if="mergeDialog.visible" class="merge-overlay" @click.self="mergeDialog.visible = false">
      <div class="merge-dialog">
        <div class="merge-dialog-header">
          <h4>合并分组「{{ mergeDialog.sourceName }}」</h4>
          <button type="button" @click="mergeDialog.visible = false">✕</button>
        </div>
        <div class="merge-dialog-body">
          <p>将「{{ mergeDialog.sourceName }}」的 {{ mergeDialog.sourceCount }} 个节点合并到目标分组：</p>
          <select v-model="mergeDialog.targetId" class="merge-select">
            <option value="">-- 选择目标分组 --</option>
            <option
              v-for="g in groupStore.groups"
              :key="g.id"
              :value="g.id"
              :disabled="g.id === groupStore.currentGroupId || g.id === 'default'"
            >
              {{ g.name }} ({{ g.count }} 节点)
            </option>
          </select>
        </div>
        <div class="merge-dialog-footer">
          <button type="button" class="btn btn-sm" @click="mergeDialog.visible = false">取消</button>
          <button type="button" class="btn btn-sm btn-primary" @click="onConfirmMerge" :disabled="!mergeDialog.targetId">确认合并</button>
        </div>
      </div>
    </div>

    <!-- 自动归类预览弹窗 -->
    <div v-if="classifyPreview.visible" class="merge-overlay" @click.self="classifyPreview.visible = false">
      <div class="merge-dialog" style="max-width:450px;max-height:60vh">
        <div class="merge-dialog-header">
          <h4>智能归类预览</h4>
          <button type="button" @click="classifyPreview.visible = false">✕</button>
        </div>
        <div class="merge-dialog-body" style="max-height:40vh;overflow-y:auto">
          <p v-if="classifyPreview.total === 0" style="color:var(--text-muted)">没有可自动归类的节点。请先为分组添加关键词。</p>
          <div v-else>
            <p style="margin-bottom:8px">共 {{ classifyPreview.total }} 个节点可自动归类：</p>
            <div v-for="d in classifyPreview.details" :key="d.nodeId" class="classify-item">
              <span class="classify-node">{{ d.nodeTitle }}</span>
              <span class="classify-arrow">→</span>
              <span
                class="classify-group"
                :style="{ color: groupStore.groups.find(g => g.id === d.groupId)?.color }"
              >{{ d.groupName }}</span>
              <span class="classify-score">{{ (d.score * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>
        <div class="merge-dialog-footer">
          <button type="button" class="btn btn-sm" @click="classifyPreview.visible = false">取消</button>
          <button type="button"
            class="btn btn-sm btn-primary"
            @click="onConfirmClassify"
            :disabled="classifyPreview.total === 0"
          >确认归类</button>
        </div>
      </div>
    </div>

    <!-- 批量操作栏 -->
    <div v-if="groupStore.batchSelectedNodes.length > 0" class="batch-bar">
      <span class="batch-label">已选 {{ groupStore.batchSelectedNodes.length }} 个节点</span>
      <div class="batch-actions">
        <select class="batch-select" @change="onBatchMove($event.target.value); $event.target.value = ''">
          <option value="">移动到...</option>
          <option v-for="g in groupStore.groups" :key="g.id" :value="g.id">{{ g.name }}</option>
        </select>
        <button type="button" class="btn btn-sm" @click="groupStore.clearBatchSelection()">取消选择</button>
      </div>
    </div>

    <!-- 可拖拽节点列表（当前分组下的节点） -->
    <div v-if="groupStore.currentGroupId !== 'all'" class="group-node-list" style="margin-top:6px">
      <div class="gnl-header">
        <span>节点列表</span>
        <button type="button" class="btn btn-sm" @click="toggleBatchMode">{{ batchMode ? '退出批量' : '批量操作' }}</button>
      </div>
      <div class="gnl-items">
        <div
          v-for="n in currentGroupNodes"
          :key="n.id"
          class="gnl-item"
          :class="{ selected: groupStore.batchSelectedNodes.includes(n.id), 'batch-mode': batchMode }"
          draggable="true"
          @dragstart="onNodeDragStart($event, n.id)"
          @click="batchMode ? groupStore.toggleBatchSelect(n.id) : null"
          :title="n.title"
        >
          <span v-if="batchMode" class="gnl-check">
            {{ groupStore.batchSelectedNodes.includes(n.id) ? '☑' : '☐' }}
          </span>
          <span class="gnl-name">{{ n.title }}</span>
          <span class="gnl-level" :style="levelBadge(n.level)">L{{ n.level }}</span>
        </div>
        <div v-if="currentGroupNodes.length === 0" class="gnl-empty">
          该分组暂无节点
        </div>
      </div>
    </div>
  </div>

  <!-- 隔离管理 -->
  <div class="panel-section" v-if="graphStore.isolatedPairs.length > 0">
    <h3>🚫 隔离管理</h3>
    <div class="isolate-info">已屏蔽的关联关系（{{ graphStore.isolatedPairs.length }} 组）</div>
    <div v-for="pair in graphStore.isolatedPairs" :key="pair.key" class="isolate-item">
      <span class="isolate-names">{{ pair.nodeA.title }} ↔ {{ pair.nodeB.title }}</span>
      <button type="button" class="btn btn-sm" @click="onRemoveIsolate(pair.nodeA.id, pair.nodeB.id)">解除隔离</button>
    </div>
  </div>

  <div class="panel-section">
    <h3>四维权重 <span class="count">α/β/γ/δ</span></h3>

    <div class="slider-row">
      <div class="sr-head">
        <span>α 关键词 Jaccard</span>
        <span class="sr-val">{{ cfg.w_alpha.toFixed(2) }}</span>
      </div>
      <el-slider v-model="cfg.w_alpha" :min="0" :max="1" :step="0.01" @input="onWeightChange" />
    </div>

    <div class="slider-row">
      <div class="sr-head">
        <span>β 语义向量余弦（核心）</span>
        <span class="sr-val">{{ cfg.w_beta.toFixed(2) }}</span>
      </div>
      <el-slider v-model="cfg.w_beta" :min="0" :max="1" :step="0.01" @input="onWeightChange" />
    </div>

    <div class="slider-row">
      <div class="sr-head">
        <span>γ 知识库推理</span>
        <span class="sr-val">{{ cfg.w_gamma.toFixed(2) }}</span>
      </div>
      <el-slider
        v-model="cfg.w_gamma"
        :min="0"
        :max="1"
        :step="0.01"
        :disabled="!cfg.corpusEnabled"
        @input="onWeightChange"
      />
    </div>

    <div class="slider-row">
      <div class="sr-head">
        <span>δ 拓扑邻居重叠</span>
        <span class="sr-val">{{ cfg.w_delta.toFixed(2) }}</span>
      </div>
      <el-slider v-model="cfg.w_delta" :min="0" :max="1" :step="0.01" @input="onWeightChange" />
    </div>

    <div class="slider-row" style="margin-top:6px">
      <div class="sr-head">
        <span>关联阈值</span>
        <span class="sr-val">{{ cfg.threshold.toFixed(2) }}</span>
      </div>
      <el-slider v-model="cfg.threshold" :min="0" :max="0.5" :step="0.01" @input="onWeightChange" />
    </div>

    <div class="btn-group" style="margin-top:8px">
      <button type="button" class="btn btn-sm" @click="resetWeights">重置默认</button>
    </div>
  </div>

  <!-- 关系图例 -->
  <div class="panel-section">
    <h3>关系类型图例</h3>
    <div class="legend-grid">
      <div class="legend-item" v-for="rt in relationTypes" :key="rt.code">
        <span class="legend-dot" :style="{ background: rt.color }"></span>
        <span class="legend-label">{{ rt.icon }} {{ rt.label }}</span>
        <span class="legend-code">{{ rt.code }}</span>
      </div>
    </div>
  </div>

  <!-- 问题与思考（独立展示） -->
  <div class="panel-section" v-if="questionsStore.unresolvedCount > 0 || questionsStore.items.length > 0">
    <h3>❓ 问题与思考（独立展示）</h3>
    <div class="questions-toggle" v-if="questionsStore.unresolvedCount > 0">
      <button type="button" class="btn btn-sm" @click="showQuestions = !showQuestions">
        {{ showQuestions ? '收起' : '展开' }} ({{ questionsStore.unresolvedCount }} 未解决)
      </button>
    </div>
    <div v-if="showQuestions || questionsStore.unresolvedCount === 0" class="questions-list">
      <div v-for="group in questionsStore.fileGroups" :key="group.fileId" class="questions-group">
        <div class="qg-header">📌 来自"{{ group.fileName }}"</div>
        <div v-for="item in group.items" :key="item.id" class="question-item">
          <div class="qi-title">
            <span
              class="qi-type"
              :class="item.type === 'question'
                ? 'qi-type-q'
                : item.type === 'thought' ? 'qi-type-t' : 'qi-type-e'"
            >
              {{ item.type === 'question' ? '问' : item.type === 'thought' ? '思' : '例' }}
            </span>
            <span class="qi-text" :title="item.rawText">{{ item.title.slice(0, 40) }}</span>
          </div>
          <div class="qi-actions" v-if="!item.resolved">
            <button type="button" class="btn btn-sm" @click="onMarkResolved(item.id)">标记已解决</button>
          </div>
          <div class="qi-actions" v-else>
            <span style="font-size:10px;color:var(--success)">✓ 已解决</span>
            <button type="button" class="btn btn-sm" @click="onMarkUnresolved(item.id)">撤销</button>
          </div>
        </div>
      </div>
    </div>
    <div class="questions-stats" style="margin-top:4px;font-size:10px;color:var(--text-muted)">
      共 {{ questionsStore.questions.length }} 问题 / {{ questionsStore.thoughts.length }} 思考
      / {{ questionsStore.examples.length }} 示例
    </div>
  </div>

  <!-- 知识点校验面板 -->
  <ValidationPanel />

  <!-- 关联质量控制 -->
  <div class="panel-section">
    <h3>🎯 关联质量控制</h3>
    <div class="aq-mode-selector">
      <button type="button"
        class="aq-mode-btn"
        :class="{ active: graphStore.associationMode === 'precise' }"
        @click="onSetAssociationMode('precise')"
      >精确模式</button>
      <button type="button"
        class="aq-mode-btn"
        :class="{ active: graphStore.associationMode === 'balanced' }"
        @click="onSetAssociationMode('balanced')"
      >均衡模式</button>
      <button type="button"
        class="aq-mode-btn"
        :class="{ active: graphStore.associationMode === 'loose' }"
        @click="onSetAssociationMode('loose')"
      >宽松模式</button>
    </div>
    <div class="aq-stats" style="margin-top:6px;font-size:11px;color:var(--text-secondary)">
      <div class="aq-stat-row">
        <span>总节点: {{ graphStore.nodeCount }}</span>
        <span>总连线: {{ graphStore.linkCount }}</span>
      </div>
      <div class="aq-stat-row">
        <span class="aq-ev aq-ev-strong">🟢 强证据: {{ graphStore.linkStats.strong }}</span>
        <span class="aq-ev aq-ev-medium">🟡 中证据: {{ graphStore.linkStats.medium }}</span>
      </div>
      <div class="aq-stat-row">
        <span class="aq-ev aq-ev-weak">🟠 弱证据: {{ graphStore.linkStats.weak }}</span>
        <span class="aq-ev aq-ev-none">🔴 无证据: {{ graphStore.linkStats.noEvidence }}</span>
      </div>
    </div>
    <div v-if="graphStore.weakLinks.length > 0" style="margin-top:6px">
      <div class="aq-warning">
        ⚠️ 待审核弱关联 ({{ graphStore.weakLinks.length }})
      </div>
      <div class="btn-group" style="margin-top:4px">
        <button type="button" class="btn btn-sm" @click="onRemoveWeakLinks">全部移除弱关联</button>
      </div>
    </div>
    <div v-if="graphStore.adoptionWarnings.length > 0" style="margin-top:6px">
      <div class="aq-warning" style="border-left-color:var(--accent)">
        📋 收养警告 ({{ graphStore.adoptionWarnings.length }})
      </div>
      <div v-for="(w, i) in graphStore.adoptionWarnings.slice(0, 3)" :key="i" class="aq-warn-item" :title="w">
        {{ w.slice(0, 60) }}{{ w.length > 60 ? '...' : '' }}
      </div>
      <div v-if="graphStore.adoptionWarnings.length > 3" style="font-size:10px;color:var(--text-muted);margin-top:2px">
        还有 {{ graphStore.adoptionWarnings.length - 3 }} 条警告...
      </div>
    </div>
  </div>

  <div class="panel-section">
    <h3>推理开关</h3>
    <div class="slider-row">
      <div class="sr-head">
        <span>知识库推理总开关（γ）</span>
        <span class="sr-val">{{ cfg.corpusEnabled ? 'ON' : 'OFF' }}</span>
      </div>
      <el-switch v-model="cfg.corpusEnabled" @change="onWeightChange" />
    </div>
    <div class="slider-row" style="margin-top:8px">
      <div class="sr-head">
        <span>显示系统知识库节点</span>
        <span class="sr-val">{{ cfg.showSystemNodes ? 'ON' : 'OFF' }}</span>
      </div>
      <el-switch v-model="cfg.showSystemNodes" @change="onSystemNodesToggle" />
    </div>
    <p style="font-size:11px;color:var(--text-muted);margin-top:4px">
      关闭后仅保留 α+β 文本/语义关联，不参与知识库桥接
    </p>
  </div>

  <div class="panel-section">
    <h3>功能按钮</h3>
    <button type="button" class="btn btn-primary btn-block" @click="onRebuildAll" :disabled="graphStore.isBusy">
      🌍 立即重排全量图谱
    </button>
    <p style="font-size:11px;color:var(--text-muted);margin-top:4px">
      触发全节点重算 + 关系重新分类 + 力导向重绘 + 全量知识点校验
    </p>
  </div>

  <!-- 插件系统 -->
  <div class="panel-section">
    <h3>插件系统 <span class="count">{{ plugins.length }}</span></h3>
    <div v-if="plugins.length === 0" class="plugin-empty">暂无插件</div>
    <div v-for="p in plugins" :key="p.id" class="plugin-card">
      <div class="plugin-head">
        <div class="plugin-info">
          <span class="plugin-name">{{ p.name }}</span>
          <span class="plugin-desc">{{ p.description }}</span>
        </div>
        <el-switch v-model="p.enabled" size="small" />
      </div>
      <div v-if="p.enabled" class="plugin-actions">
        <div v-if="p.exports.length" class="plugin-group">
          <span class="plugin-group-label">导出</span>
          <div class="plugin-btns">
            <button type="button" v-for="e in p.exports" :key="e.label" class="btn btn-sm" @click="e.fn()">{{ e.label }}</button>
          </div>
        </div>
        <div v-if="p.commands.length" class="plugin-group">
          <span class="plugin-group-label">命令</span>
          <div class="plugin-btns">
            <button type="button" v-for="c in p.commands" :key="c.label" class="btn btn-sm" @click="c.fn()">{{ c.label }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="panel-section">
    <h3>异常节点监控</h3>
    <div class="monitor-grid">
      <div class="monitor-card" :class="{ ok: graphStore.orphanCount === 0, warn: graphStore.orphanCount > 0 }">
        <div class="mc-num">{{ graphStore.orphanCount }}</div>
        <div class="mc-label">孤立节点（必须为0）</div>
      </div>
      <div class="monitor-card">
        <div class="mc-num">{{ graphStore.nodeCount }}</div>
        <div class="mc-label">总节点</div>
      </div>
      <div class="monitor-card">
        <div class="mc-num">{{ graphStore.linkCount }}</div>
        <div class="mc-label">总连线</div>
      </div>
      <div class="monitor-card">
        <div class="mc-num">{{ engineLabel }}</div>
        <div class="mc-label">向量引擎</div>
      </div>
      <div class="monitor-card" :class="{ warn: graphStore.validationPendingCount > 0 }">
        <div
          class="mc-num"
          :style="{ color: graphStore.validationPendingCount > 0 ? 'var(--danger)' : 'var(--success)' }"
        >
          {{ graphStore.validationPendingCount }}
        </div>
        <div class="mc-label">待处理异常</div>
      </div>
    </div>
  </div>

  <div class="panel-section">
    <h3>状态</h3>
    <div class="status-bar" :class="{ 'is-busy': graphStore.isBusy }">
      <span class="dot"></span>
      <span>{{ graphStore.busy || '空闲' }}</span>
      <span
        v-if="graphStore.busyProgress > 0 && graphStore.busyProgress < 100"
        style="margin-left:auto;color:var(--accent)"
      >
        {{ graphStore.busyProgress }}%
      </span>
    </div>
    <!-- 降级提示条 -->
    <div v-if="cfg.vectorEngineMode === 'fallback-tfidf'" class="degraded-banner">
      ⚠ 当前使用降级向量模式（TF-IDF 100维），语义能力受限
    </div>
    <div v-else-if="cfg.vectorEngineMode === 'fallback-ngram'" class="degraded-banner">
      ⚠ 当前使用降级向量模式（n-gram 哈希），仅支持字面匹配
    </div>
    <!-- 韧性架构：系统健康状态 -->
    <div v-if="healthWarnings.length > 0" class="health-warnings">
      <div v-for="(w, i) in healthWarnings" :key="i" class="health-warning-item" :class="'health-' + w.level">
        <span class="health-icon">{{ w.level === 'error' ? '🔴' : w.level === 'warn' ? '🟡' : '🔵' }}</span>
        <span>{{ w.msg }}</span>
      </div>
    </div>
    <div class="health-indicator" :class="healthStatus">
      <span class="health-dot"></span>
      <span>{{ healthStatus === 'healthy' ? '系统健康' : healthStatus === 'warning' ? '需要注意' : '系统异常' }}</span>
      <span class="health-meta">节点 {{ graphStore.nodeCount }} | 连线 {{ graphStore.linkCount }}</span>
    </div>
  </div>

  <!-- 知识校验状态总览 -->
  <div class="panel-section">
    <h3>🔍 知识校验状态</h3>
    <div class="validation-overview">
      <div class="val-stat-row">
        <span class="val-stat-label">✅ 已验证</span>
        <span class="val-stat-value val-passed">{{ graphStore.validationStats.passed }}</span>
      </div>
      <div class="val-stat-row">
        <span class="val-stat-label">⚠️ 待审查</span>
        <span class="val-stat-value val-warning">{{ graphStore.validationStats.warning }}</span>
      </div>
      <div class="val-stat-row">
        <span class="val-stat-label">❌ 存在错误</span>
        <span class="val-stat-value val-error">{{ graphStore.validationStats.error }}</span>
      </div>
      <div class="val-stat-row">
        <span class="val-stat-label">⏳ 待校验</span>
        <span class="val-stat-value val-pending">{{ graphStore.validationStats.pending }}</span>
      </div>
      <div class="val-stat-divider"></div>
      <div class="val-stat-row">
        <span class="val-stat-label">正确率</span>
        <span class="val-stat-value" :class="accuracyClass">{{ graphStore.validationStats.accuracy }}%</span>
      </div>
    </div>
    <!-- 未通过校验节点列表 -->
    <div v-if="graphStore.unverifiedNodes.length > 0" class="val-unverified-list" style="margin-top:6px">
      <div class="val-unverified-header">
        <span>⚠️ 未通过校验的节点（{{ graphStore.unverifiedNodes.length }}）</span>
      </div>
      <div class="val-unverified-items">
        <div v-for="n in graphStore.unverifiedNodes.slice(0, 5)" :key="n.id" class="val-unverified-item">
          <span class="val-unverified-status" :style="{ color: getNodeValidationStatus(n).color }">
            {{ getNodeValidationStatus(n).label }}
          </span>
          <span class="val-unverified-title">{{ n.title }}</span>
        </div>
        <div v-if="graphStore.unverifiedNodes.length > 5" class="val-unverified-more">
          ...还有 {{ graphStore.unverifiedNodes.length - 5 }} 个节点待校验
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '@/store/configStore'
import { useGraphStore } from '@/store/graphStore'
import { useNoteStore } from '@/store/noteStore'
import { useFileStore } from '@/store/fileStore'
import { useGroupStore, GROUP_COLORS } from '@/store/groupStore'
import { useQuestionsStore } from '@/store/questionsStore'
import { getAllRelationTypes } from '@/utils/relationClassifier'
import { getLevelInfo, getLevelColor } from '@/utils/mdParser'
import { HealthMonitor, debounce } from '@/utils/resilience'
import { getNodeValidationStatus } from '@/utils/noteValidator'
import { plugins, setPluginContext, activatePlugins } from '@/plugins/registry'
import '@/plugins'
import ValidationPanel from './ValidationPanel.vue'
import GroupTreeNode from './GroupTreeNode.vue'

const cfg = useConfigStore()
const graphStore = useGraphStore()
const noteStore = useNoteStore()
const fileStore = useFileStore()
const groupStore = useGroupStore()
const questionsStore = useQuestionsStore()

const relationTypes = getAllRelationTypes()

// 分组视图模式：tree | flat
const groupViewMode = ref('flat')

// 批量选择模式
const batchMode = ref(false)
// 拖拽中的节点ID
const draggingNodeId = ref(null)
// 拖拽悬停中的分组ID
const dragOverGroupId = ref(null)

// 分组编辑弹窗
const editDialog = ref({
  visible: false,
  name: '',
  description: '',
  keywordsStr: '',
  parentId: null
})

// 分组合并弹窗
const mergeDialog = ref({
  visible: false,
  sourceName: '',
  sourceCount: 0,
  targetId: ''
})

// 自动归类预览弹窗
const classifyPreview = ref({
  visible: false,
  total: 0,
  details: []
})

// 分组分布展开状态
const showGroupDist = ref(false)

// 分组分布最大节点数
const maxCount = computed(() => {
  return Math.max(1, ...groupStore.visibleGroups.map(g => g.count || 0))
})

// 隐藏的分组数量
const hiddenGroupCount = computed(() => {
  return groupStore.groups.filter(g => g.visible === false).length
})

// 当前分组描述
const currentGroupDesc = computed(() => {
  const g = groupStore.groups.find(g => g.id === groupStore.currentGroupId)
  return g?.description || ''
})

// === 韧性架构：健康监控 ===
const healthMonitor = new HealthMonitor()
const healthStatus = ref('healthy')
const healthWarnings = ref([])

healthMonitor.onUpdate((metrics, warnings) => {
  healthMonitor.updateStoreMetrics(graphStore.nodes, graphStore.links, 0)
  healthStatus.value = healthMonitor.getStatus()
  healthWarnings.value = [...warnings]
})

// === 韧性架构：防抖权重变更 ===
const onWeightChange = debounce(() => {
  graphStore.recomputeScoreOnly()
  graphStore.version++
  graphStore.restartTick++
}, 500)

const engineLabel = computed(() => {
  return '后端'
})

const accuracyClass = computed(() => {
  const acc = graphStore.validationStats.accuracy
  if (acc >= 80) return 'val-passed'
  if (acc >= 50) return 'val-warning'
  return 'val-error'
})

// 当前分组下的节点列表
const currentGroupNodes = computed(() => {
  const gid = groupStore.currentGroupId
  if (gid === 'all') return []
  return graphStore.nodes.filter(n => n.groupId === gid)
})

// 分组标签样式（含颜色）
function groupTabStyle(g) {
  return {
    borderColor: groupStore.currentGroupId === g.id ? g.color : 'transparent',
    background: groupStore.currentGroupId === g.id ? (g.color + '20') : 'transparent',
    opacity: g.visible === false ? 0.5 : 1
  }
}

// 层级角标样式（色值统一取自 mdParser 层级体系）
function levelBadge(lv) {
  return {
    background: getLevelColor(lv),
    color: '#fff',
    fontSize: '9px',
    padding: '1px 4px',
    borderRadius: '3px'
  }
}

// 获取分组路径（用于父分组选择器）
function getGroupPath(g) {
  const ancestors = groupStore.ancestorChain(g.id)
  return [...ancestors.map(a => a.name), g.name].join(' > ')
}

// 检查目标分组是否是源分组的后代（防止循环）
function isDescendantOf(targetId, sourceId) {
  const descendants = groupStore.descendantsOf(sourceId)
  return descendants.some(d => d.id === targetId)
}

// === 问题与思考 ===
const showQuestions = ref(false)

function onMarkResolved(itemId) {
  questionsStore.markResolved(itemId)
  ElMessage.success('已标记为已解决')
}

function onMarkUnresolved(itemId) {
  questionsStore.markUnresolved(itemId)
  ElMessage.info('已撤销')
}

function onSystemNodesToggle() {
  graphStore.version++
  ElMessage.success(cfg.showSystemNodes ? '已显示系统知识库节点' : '已隐藏系统知识库节点')
}

function resetWeights() {
  cfg.resetWeights()
  onWeightChange()
  ElMessage.success('权重已重置为默认最优配比')
}

async function onRebuildAll() {
  if (graphStore.nodeCount === 0) {
    ElMessage.warning('暂无节点，请先上传文档')
    return
  }
  ElMessage.info('开始全量重排...')
  const res = await graphStore.rebuildAll()
  const warnMsg = res.ok !== undefined ? `重排完成：连线 ${res.ok} 条，孤立节点 ${res.orphanCount}` : '重排完成'
  ElMessage.success(warnMsg)
}

// === 关联质量控制 ===
function onSetAssociationMode(mode) {
  graphStore.setAssociationMode(mode)
  const labels = { precise: '精确模式', balanced: '均衡模式', loose: '宽松模式' }
  ElMessage.success(`已切换为「${labels[mode] || mode}」`)
}

function onRemoveWeakLinks() {
  if (!confirm('确定要移除所有弱证据关联吗？此操作不可撤销。')) return
  const res = graphStore.removeWeakLinks()
  ElMessage.success(`已移除 ${res.removed} 条弱证据关联`)
}

// === 分组管理 ===
function onSwitchGroup(groupId) {
  groupStore.switchGroup(groupId)
  graphStore.version++
  graphStore.restartTick++
  ElMessage.success(`已切换到「${groupStore.currentGroup.name}」`)
}

function onNewGroup() {
  const name = prompt('请输入新分组名称：')
  if (!name?.trim()) return
  const g = groupStore.createGroup(name)
  if (g) ElMessage.success(`分组「${g.name}」已创建`)
}

function onRenameGroup() {
  const gid = groupStore.currentGroupId
  const g = groupStore.groups.find(g => g.id === gid)
  const name = prompt('请输入新名称：', g?.name || '')
  if (!name?.trim()) return
  if (groupStore.renameGroup(gid, name)) {
    graphStore.version++
    ElMessage.success('分组已重命名')
  }
}

function onDeleteGroup() {
  if (!confirm('删除分组不会删除节点，节点将归入"默认分组"。确认删除？')) return
  groupStore.deleteGroup(groupStore.currentGroupId)
  graphStore.version++
  graphStore.restartTick++
  ElMessage.success('分组已删除，节点归入默认分组')
}

// === 分组编辑 ===
function onEditGroup() {
  const gid = groupStore.currentGroupId
  const g = groupStore.groups.find(g => g.id === gid)
  if (!g) return
  editDialog.value = {
    visible: true,
    name: g.name,
    description: g.description || '',
    keywordsStr: (g.keywords || []).join(', '),
    parentId: g.parentId || null
  }
}

function onConfirmEdit() {
  const gid = groupStore.currentGroupId
  // 保存描述
  groupStore.setGroupDescription(gid, editDialog.value.description)
  // 保存关键词
  const keywords = editDialog.value.keywordsStr
    .split(/[,，]/)
    .map(k => k.trim())
    .filter(k => k.length > 0)
  groupStore.setGroupKeywords(gid, keywords)
  // 保存父分组
  if (editDialog.value.parentId !== undefined) {
    groupStore.setParentGroup(gid, editDialog.value.parentId)
  }
  graphStore.version++
  editDialog.value.visible = false
  ElMessage.success('分组设置已保存')
}

// === 分组合并 ===
function onMergeGroup() {
  const gid = groupStore.currentGroupId
  const g = groupStore.groups.find(g => g.id === gid)
  if (!g) return
  mergeDialog.value = {
    visible: true,
    sourceName: g.name,
    sourceCount: g.count,
    targetId: ''
  }
}

function onConfirmMerge() {
  const gid = groupStore.currentGroupId
  const targetId = mergeDialog.value.targetId
  if (!targetId || gid === targetId) return
  const result = groupStore.mergeGroups(gid, targetId)
  if (result.ok) {
    graphStore.version++
    graphStore.restartTick++
    ElMessage.success(`已将「${result.sourceName}」的 ${result.mergedCount} 个节点合并到「${result.targetName}」`)
    mergeDialog.value.visible = false
  } else {
    ElMessage.warning(result.reason || '合并失败')
  }
}

// === 分组可见性 ===
function onToggleVisibility(groupId) {
  const nowVisible = groupStore.toggleGroupVisibility(groupId)
  graphStore.version++
  graphStore.restartTick++
  const g = groupStore.groups.find(g => g.id === groupId)
  ElMessage.info(nowVisible ? `「${g?.name}」已显示` : `「${g?.name}」已隐藏`)
}

function onShowAllGroups() {
  groupStore.showAllGroups()
  graphStore.version++
  graphStore.restartTick++
  ElMessage.success('所有分组已显示')
}

// === 自动归类 ===
function onAutoClassify() {
  const result = groupStore.autoClassifyNodes()
  if (result.msg) {
    ElMessage.warning(result.msg)
    return
  }
  if (result.classified > 0) {
    graphStore.version++
    graphStore.restartTick++
    ElMessage.success(`已自动归类 ${result.classified} 个节点`)
  } else {
    ElMessage.info('没有可自动归类的节点')
  }
}

function onPreviewClassify() {
  const result = groupStore.previewAutoClassify()
  classifyPreview.value = {
    visible: true,
    total: result.total,
    details: result.details
  }
}

function onConfirmClassify() {
  const result = groupStore.autoClassifyNodes()
  if (result.classified > 0) {
    graphStore.version++
    graphStore.restartTick++
    ElMessage.success(`已自动归类 ${result.classified} 个节点`)
  }
  classifyPreview.value.visible = false
}

// === 分组搜索 ===
function onGroupSearch(keyword) {
  groupStore.setSearch(keyword)
}

// 当前分组颜色（供取色器回显）
const currentGroupColor = computed(() => {
  const g = groupStore.groups.find(g => g.id === groupStore.currentGroupId)
  return g?.color || GROUP_COLORS[0]
})

// === 分组颜色选择（el-color-picker + 既有 12 色预定义色板）===
function onGroupColorChange(color) {
  if (!color) return
  const gid = groupStore.currentGroupId
  groupStore.setGroupColor(gid, color)
  graphStore.version++
  ElMessage.success('分组颜色已更新')
}

// === 拖拽节点到分组 ===
function onNodeDragStart(event, nodeId) {
  draggingNodeId.value = nodeId
  event.dataTransfer.setData('text/plain', nodeId)
  event.dataTransfer.effectAllowed = 'move'
}

function onGroupDragOver(event, groupId) {
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dragOverGroupId.value = groupId
  if (event.target) event.target.classList.add('drag-over')
}

function onGroupDragLeave(event) {
  dragOverGroupId.value = null
  if (event.target) event.target.classList.remove('drag-over')
}

function onGroupDrop(event, groupId) {
  event.preventDefault()
  if (event.target) event.target.classList.remove('drag-over')
  const nodeId = draggingNodeId.value || event.dataTransfer.getData('text/plain')
  if (nodeId && groupId) {
    const result = groupStore.dropNodeToGroup(nodeId, groupId)
    if (result) {
      graphStore.version++
      graphStore.restartTick++
      const group = groupStore.groups.find(g => g.id === groupId)
      const node = graphStore.nodes.find(n => n.id === nodeId)
      ElMessage.success(`"${node?.title || nodeId}" 已移动到「${group?.name || groupId}」`)
    }
  }
  draggingNodeId.value = null
  dragOverGroupId.value = null
}

// === 批量操作 ===
function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) {
    groupStore.clearBatchSelection()
  }
}

function onBatchMove(groupId) {
  if (!groupId) return
  const count = groupStore.batchMoveToGroup(groupStore.batchSelectedNodes, groupId)
  if (count > 0) {
    graphStore.version++
    graphStore.restartTick++
    const group = groupStore.groups.find(g => g.id === groupId)
    ElMessage.success(`已将 ${count} 个节点移动到「${group?.name || groupId}」`)
    groupStore.clearBatchSelection()
    batchMode.value = false
  }
}

// === 隔离管理 ===
function onRemoveIsolate(nodeIdA, nodeIdB) {
  graphStore.removeIsolate(nodeIdA, nodeIdB)
  ElMessage.success('已解除隔离，下次图谱更新时重新计算关联')
}

onMounted(() => {
  // 启动健康监控
  healthMonitor.startMonitoring(10000)
  // 初始化插件系统：注入上下文并激活内置插件
  setPluginContext({ graphStore, noteStore, fileStore })
  activatePlugins()
})

onUnmounted(() => {
  healthMonitor.stopMonitoring()
})
</script>

<style scoped>
/* ============================================================
   控制面板内部视觉统一（亮/暗双主题自适应）
   scoped：只作用于本组件自身元素，不影响 ValidationPanel 等子组件
   ============================================================ */

/* 1) 区块小标题：弱色 + 加宽字距 + 细分隔 */
.panel-section h3 {
  letter-spacing: 0.8px;
  padding-bottom: 7px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border-light);
}
.panel-section h3 .count {
  background: var(--accent-soft);
  color: var(--accent-strong);
  font-family: var(--font-mono);
  font-weight: 600;
  padding: 1px 8px;
}

/* 2) 小卡片底座：白卡 + 细边框 + 柔和阴影 */
.group-distribution,
.group-node-list,
.validation-overview,
.monitor-card,
.legend-item,
.status-bar,
.health-indicator,
.hidden-groups-notice,
.isolate-item,
.val-unverified-list {
  border-radius: var(--radius);
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
  box-shadow: var(--shadow-sm);
}

/* 统计卡 / 图例项：悬浮轻微上浮 */
.monitor-card,
.legend-item {
  transition: transform var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}
.monitor-card:hover,
.legend-item:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-card);
  border-color: var(--border);
}

/* 3) 状态条 / 健康指示（语义色 + 光晕点） */
.status-bar { border-radius: var(--radius); padding: 6px 10px; }
.status-bar .dot { box-shadow: 0 0 0 3px var(--success-soft); }
.status-bar.is-busy {
  border-color: var(--warning-soft);
  background: var(--warning-soft);
}
.status-bar.is-busy .dot { box-shadow: 0 0 0 3px var(--warning-soft); }

.health-indicator { border-radius: var(--radius); padding: 6px 10px; }
.health-indicator.healthy { color: var(--success); }
.health-indicator.warning { color: var(--warning); }
.health-indicator.error { color: var(--danger); }
.health-indicator .health-dot { box-shadow: 0 0 0 3px var(--success-soft); }
.health-indicator.warning .health-dot { box-shadow: 0 0 0 3px var(--warning-soft); }
.health-indicator.error .health-dot { box-shadow: 0 0 0 3px var(--danger-soft); }
.health-meta { font-family: var(--font-mono); }

.health-warning-item { border-radius: var(--radius-sm); padding: 4px 9px; }
.health-warning-item.health-warn { background: var(--warning-soft); color: var(--warning); }
.health-warning-item.health-error { background: var(--danger-soft); color: var(--danger); }
.health-warning-item.health-info { background: var(--accent-soft); color: var(--accent); }

.degraded-banner {
  background: var(--warning-soft);
  color: var(--warning);
  border: 1px solid var(--warning-soft);
  border-radius: var(--radius-sm);
  font-weight: 500;
}

/* 4) 模式切换 / 小按钮组：统一圆角 + 悬浮与点击反馈 */
.aq-mode-btn {
  border-radius: var(--radius-sm);
  font-weight: 500;
  transition: background-color var(--dur-fast), border-color var(--dur-fast),
    color var(--dur-fast), box-shadow var(--dur-fast), transform 0.12s var(--ease-out);
}
.aq-mode-btn:hover { border-color: var(--accent); color: var(--text-primary); background: var(--bg-hover); }
.aq-mode-btn:active { transform: scale(0.96); }
.aq-mode-btn.active {
  background: var(--accent-soft);
  color: var(--accent-strong);
  border-color: var(--accent);
  font-weight: 600;
}

.view-toggle-btn,
.sort-btn { border-radius: var(--radius-sm); transition: all var(--dur-fast); }
.view-toggle-btn:hover { color: var(--accent); border-color: var(--accent); }
.view-toggle-btn.active { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
.sort-btn:hover { color: var(--accent); border-color: var(--accent); }
.sort-btn.active { color: var(--accent-strong); background: var(--accent-soft); border-color: var(--accent); }
.group-collapse-btn:hover { color: var(--accent); }

.group-tab { border-radius: var(--radius-full); }
.group-tab:hover { border-color: var(--accent); }
.group-tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent-strong); }

/* 5) 输入/选择控件：聚焦光环一致 */
.group-search,
.merge-select,
.batch-select,
.edit-input,
.edit-textarea {
  border-radius: var(--radius-sm);
  transition:
    border-color var(--dur-fast),
    box-shadow var(--dur-fast);
}
.group-search:focus,
.merge-select:focus,
.batch-select:focus,
.edit-input:focus,
.edit-textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

/* 6) 关联质量控制：证据胶囊 + 告警块 */
.aq-stat-row { margin: 3px 0; }
.aq-ev {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
}
.aq-ev-strong { background: var(--success-soft); color: var(--success); }
.aq-ev-medium { background: var(--warning-soft); color: var(--warning); }
.aq-ev-weak { background: var(--apricot-soft); color: var(--apricot-strong); }
.aq-ev-none { background: var(--danger-soft); color: var(--danger); }

.aq-warning {
  background: var(--warning-soft);
  color: var(--warning);
  border-radius: var(--radius-sm);
  padding: 5px 10px;
  font-weight: 500;
}
.aq-warn-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  padding: 4px 9px;
  transition: border-color var(--dur-fast), background-color var(--dur-fast);
}
.aq-warn-item:hover { border-color: var(--warning); background: var(--warning-soft); }

/* 7) 批量操作条 / 分组节点列表 / 分组分布 */
.batch-bar {
  border-radius: var(--radius);
  background: var(--accent-soft);
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
  padding: 7px 10px;
}

.group-node-list { border-radius: var(--radius); overflow: hidden; }
.gnl-header {
  background: var(--bg-tertiary);
  border-radius: var(--radius) var(--radius) 0 0;
  font-weight: 500;
}
.gnl-item {
  border-left: 2px solid transparent;
  padding: 5px 8px;
  transition: background-color var(--dur-fast), border-color var(--dur-fast);
}
.gnl-item:hover { background: var(--bg-hover); }
.gnl-item.selected {
  background: var(--accent-soft);
  border-left-color: var(--accent);
  color: var(--text-primary);
}
.gnl-check { font-family: var(--font-mono); font-weight: 700; }
.gnl-empty {
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  margin: 8px;
}

.group-distribution { border-radius: var(--radius); overflow: hidden; }
.gd-header { border-radius: var(--radius) var(--radius) 0 0; font-weight: 500; }
.gd-header:hover { color: var(--accent); background: var(--bg-hover); }
.gd-summary { font-family: var(--font-mono); }

/* 8) 问题与思考（原为未样式块，补上统一质感） */
.questions-group { margin-bottom: 6px; }
.qg-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 4px 9px;
  margin-bottom: 4px;
  background: var(--bg-tertiary);
  border-left: 2px solid var(--accent);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.question-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
  padding: 7px 9px;
  margin-bottom: 4px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast),
    transform var(--dur-fast) var(--ease-out);
}
.question-item:hover { border-color: var(--border); box-shadow: var(--shadow-card); }
.qi-title { display: flex; align-items: center; gap: 6px; min-width: 0; }
.qi-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-primary);
}
.qi-type {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  border-radius: var(--radius-sm);
}
.qi-type-q { background: var(--warning-soft); color: var(--warning); }
.qi-type-t { background: var(--accent-soft); color: var(--accent-strong); }
.qi-type-e { background: var(--bg-tertiary); color: var(--text-secondary); }

/* 9) 校验总览 / 隔离管理 */
.validation-overview { padding: 8px 10px; }
.val-stat-row { padding: 3px 0; }
.val-stat-value { font-family: var(--font-mono); font-size: 12px; }

.val-unverified-list { border: none; border-radius: var(--radius); overflow: hidden; }
.val-unverified-item { padding: 4px 10px; transition: background-color var(--dur-fast); }
.val-unverified-item:hover { background: var(--bg-hover); }
.val-unverified-status { font-family: var(--font-mono); }
.val-unverified-title { color: var(--text-primary); }

.isolate-info { color: var(--text-muted); }
.isolate-item { border-radius: var(--radius-sm); transition: border-color var(--dur-fast); }
.isolate-item:hover { border-color: var(--danger); }

/* 10) 滑块/开关：悬浮光晕反馈（EP 内部节点经 :deep） */
.slider-row :deep(.el-slider:not(.is-disabled):hover .el-slider__runway),
.slider-row :deep(.el-slider.is-dragging .el-slider__runway) {
  box-shadow: 0 0 0 4px var(--accent-soft);
}
.slider-row :deep(.el-switch:not(.is-disabled):hover .el-switch__core) {
  box-shadow: 0 0 0 4px var(--accent-soft);
}

/* 11) 弹窗类小浮层 */
.merge-dialog {
  border-radius: var(--radius-lg);
  background: var(--bg-glass-strong);
  backdrop-filter: blur(18px) saturate(1.2);
  -webkit-backdrop-filter: blur(18px) saturate(1.2);
}
.merge-dialog-header h4 { letter-spacing: 0.3px; }
.merge-dialog-header button {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  transition: background-color var(--dur-fast), color var(--dur-fast);
}
.merge-dialog-header button:hover { background: var(--bg-hover); color: var(--text-primary); }
.classify-item { transition: background-color var(--dur-fast); }
.classify-item:hover { background: var(--bg-hover); }
.classify-score { font-family: var(--font-mono); }

/* 12) 插件系统 */
.plugin-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  padding: 10px;
  margin-bottom: 8px;
  transition: border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.plugin-card:last-child { margin-bottom: 0; }
.plugin-card:hover { border-color: var(--border); box-shadow: var(--shadow-sm); }
.plugin-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.plugin-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.plugin-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.plugin-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}
.plugin-actions {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-light);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.plugin-group-label {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.plugin-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
}
.plugin-empty {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px dashed var(--border-light);
  border-radius: var(--radius);
}
</style>