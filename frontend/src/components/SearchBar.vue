<!-- 搜索栏组件 — 带搜索图标前缀的输入框，触发搜索和清除事件 -->
<template>
  <div class="search-bar">
    <el-input
      v-model="searchText"
      placeholder="搜索对话..."
      clearable
      @input="handleSearch"
      @clear="handleClear"
    >
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
    </el-input>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

interface Emits {
  (e: 'search', keyword: string): void
  (e: 'clear'): void
}

const emit = defineEmits<Emits>()

const searchText = ref('')

const handleSearch = () => {
  emit('search', searchText.value)
}

const handleClear = () => {
  searchText.value = ''
  emit('clear')
}
</script>

<style scoped>
.search-bar {
  padding: 10px;
  border-bottom: 1px solid #e4e7ed;
}
</style>

