<template>
  <div class="tree-branch">
    <div
      class="tree-item"
      :class="{ active: currentGroupId === node.id, hidden: node.visible === false }"
      :style="{ paddingLeft: (depth * 16 + 8) + 'px' }"
      @click="$emit('switch-group', node.id)"
      @dragover.prevent="$emit('drag-over', $event, node.id)"
      @dragleave="$emit('drag-leave', $event)"
      @drop="$emit('drop', $event, node.id)"
      :title="node.description || node.name"
    >
      <span v-if="node.children && node.children.length > 0" class="tree-toggle" @click.stop="$emit('toggle-collapse', node.id)">{{ treeCollapsed[node.id] ? '▶' : '▼' }}</span>
      <span v-else class="tree-toggle tree-toggle-empty"></span>
      <span class="tree-visibility" @click.stop="$emit('toggle-visibility', node.id)" :title="node.visible === false ? '点击显示' : '点击隐藏'">{{ node.visible === false ? '🚫' : '👁' }}</span>
      <span class="tree-color-dot" :style="{ background: node.color }"></span>
      <span class="tree-name">{{ node.name }}</span>
      <span class="tree-count">{{ node.count }}</span>
      <span v-if="node.children && node.children.length > 0" class="tree-children-count">+{{ node.children.length }}</span>
    </div>
    <template v-if="node.children && node.children.length > 0 && !treeCollapsed[node.id]">
      <GroupTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :tree-collapsed="treeCollapsed"
        :current-group-id="currentGroupId"
        @switch-group="id => $emit('switch-group', id)"
        @toggle-collapse="id => $emit('toggle-collapse', id)"
        @toggle-visibility="id => $emit('toggle-visibility', id)"
        @drag-over="(e, id) => $emit('drag-over', e, id)"
        @drag-leave="e => $emit('drag-leave', e)"
        @drop="(e, id) => $emit('drop', e, id)"
      />
    </template>
  </div>
</template>

<script setup>
defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  treeCollapsed: { type: Object, default: () => ({}) },
  currentGroupId: { type: String, default: 'all' }
})

defineEmits(['switch-group', 'toggle-collapse', 'toggle-visibility', 'drag-over', 'drag-leave', 'drop'])
</script>
