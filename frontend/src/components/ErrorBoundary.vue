<!-- 错误边界组件 — 捕获子组件渲染错误，显示全页错误提示和刷新按钮 -->
<template>
  <div v-if="hasError" class="error-boundary">
    <el-result
      icon="error"
      title="出现错误"
      sub-title="页面加载时出现错误，请刷新页面重试"
    >
      <template #extra>
        <el-button type="primary" @click="handleReset">刷新页面</el-button>
      </template>
    </el-result>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { ElMessage } from 'element-plus'

const hasError = ref(false)

onErrorCaptured((err, instance, info) => {
  console.error('Error caught by boundary:', err, info)
  hasError.value = true
  ElMessage.error('页面出现错误，请刷新重试')
  return false
})

const handleReset = () => {
  window.location.reload()
}
</script>

<style scoped>
.error-boundary {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}
</style>

