<!-- 角色卡片组件 — 可选择 AI 角色卡片，展示头像、名称、ID、类型标签（内置/自定义）、描述和收藏按钮 -->
<template>
  <div
    class="role-card"
    :class="{ 'selected': isSelected }"
    @click="handleClick"
  >
    <div class="card-bg"></div>
    <div class="card-content">
      <div class="card-header">
        <div class="avatar-wrapper">
          <span class="avatar-text">{{ role.name.charAt(0) }}</span>
        </div>
        <div class="role-meta">
          <div class="name-row">
            <h3>{{ role.name }}</h3>
            <div class="header-right">
              <el-tag 
                :type="role.roleType === 'BUILTIN' ? 'primary' : 'success'" 
                size="small"
                effect="dark"
                class="role-tag"
              >
                {{ role.roleType === 'BUILTIN' ? '内置' : '自定义' }}
              </el-tag>
              <div 
                class="favorite-btn" 
                :class="{ active: isFavorite }"
                @click.stop="handleToggleFavorite"
              >
                <el-icon v-if="isFavorite"><StarFilled /></el-icon>
                <el-icon v-else><Star /></el-icon>
              </div>
            </div>
          </div>
          <span class="role-id">ID: {{ role.id.substring(0, 8) }}</span>
        </div>
      </div>
      
      <div class="card-body">
        <p class="description">{{ role.description || '暂无描述' }}</p>
      </div>

      <div class="card-footer">
        <div class="status-indicator" :class="{ active: isSelected }">
          <span class="dot"></span>
          {{ isSelected ? '当前使用' : '点击切换' }}
        </div>
        
        <div v-if="role.roleType === 'CUSTOM'" class="actions">
          <el-tooltip content="编辑角色" placement="top" :show-after="500">
            <button class="icon-btn edit" @click.stop="handleEdit">
              <el-icon><EditPen /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip content="删除角色" placement="top" :show-after="500">
            <button class="icon-btn delete" @click.stop="handleDelete">
              <el-icon><Delete /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { EditPen, Delete, Star, StarFilled } from '@element-plus/icons-vue'
import type { Role } from '@/services/api/role'
import { useRoleStore } from '@/stores/role'

interface Props {
  role: Role
  selected?: boolean
}

interface Emits {
  (e: 'select', role: Role): void
  (e: 'edit', role: Role): void
  (e: 'delete', role: Role): void
}

const props = withDefaults(defineProps<Props>(), {
  selected: false
})

const emit = defineEmits<Emits>()
const roleStore = useRoleStore()

const isSelected = computed(() => props.selected)
const isFavorite = computed(() => roleStore.favorites.includes(props.role.id))

const handleToggleFavorite = () => {
  roleStore.toggleFavorite(props.role.id)
}

const handleClick = () => {
  emit('select', props.role)
}

const handleEdit = () => {
  emit('edit', props.role)
}

const handleDelete = () => {
  emit('delete', props.role)
}
</script>

<style scoped lang="scss">
// 变量定义 - 简洁优雅的设计系统
$primary-color: var(--primary-color);
$primary-light: var(--primary-fade);
$border-color: var(--border-light);
$border-light: var(--border-light);
$shadow-subtle: 0 2px 8px rgba(0, 0, 0, 0.04);
$shadow-hover: 0 4px 16px rgba(0, 0, 0, 0.06);

.role-card {
  position: relative;
  height: 200px;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  border: 1px solid $border-color;
  background: color-mix(in srgb, var(--bg-card) 85%, transparent);
  backdrop-filter: blur(20px);
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: $shadow-hover;
    background: color-mix(in srgb, var(--bg-card) 95%, transparent);
    border-color: var(--primary-line);
    
    .card-footer {
      background: var(--bg-panel);
    }
  }
  
  &.selected {
    border-color: $primary-color;
    box-shadow: 0 0 0 2px var(--primary-line), $shadow-hover;
    background: color-mix(in srgb, var(--bg-card) 95%, transparent);
    
    .status-indicator {
      color: $primary-color;
      
      .dot {
        background: $primary-color;
        box-shadow: 0 0 0 2px var(--primary-line);
      }
    }
  }
}

.card-content {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px;
}

.card-header {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  
  .avatar-wrapper {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 20px;
    font-weight: 600;
    box-shadow: $shadow-subtle;
    letter-spacing: -0.01em;
  }
  
  .role-meta {
    flex: 1;
    min-width: 0;
    
    .name-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
      
      h3 {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
        color: var(--text-primary);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        letter-spacing: -0.01em;
        line-height: 1.2;
      }
      
      .role-tag {
        border: none;
        height: 20px;
        padding: 0 8px;
        font-size: 11px;
        font-weight: 500;
        letter-spacing: 0.01em;
      }

      .header-right {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .favorite-btn {
        font-size: 18px;
        color: #d1d5db;
        cursor: pointer;
        transition: all 0.2s;
        display: flex;
        align-items: center;

        &:hover {
          color: #f59e0b;
          transform: scale(1.1);
        }

        &.active {
          color: #f59e0b;
        }
      }
    }
    
    .role-id {
      font-size: 11px;
      color: var(--text-secondary);
      font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
      font-weight: 400;
      letter-spacing: 0.01em;
    }
  }
}

.card-body {
  flex: 1;
  
  .description {
    margin: 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-regular);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-weight: 400;
    letter-spacing: 0.01em;
  }
}

.card-footer {
  margin: 0 -20px -20px -20px;
  padding: 14px 20px;
  background: var(--bg-panel);
  border-top: 1px solid $border-light;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: background 0.25s;
  
  .status-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-secondary);
    letter-spacing: 0.01em;
    
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--border-light);
      transition: all 0.25s;
    }
  }
  
  .actions {
    display: flex;
    gap: 6px;
    
    .icon-btn {
      width: 28px;
      height: 28px;
      border-radius: 8px;
      border: none;
      background: transparent;
      color: var(--text-secondary);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
      
      &:hover {
        background: rgba(0, 0, 0, 0.05);
        
        &.edit { 
          color: #3b82f6;
          background: rgba(59, 130, 246, 0.1);
        }
        &.delete { 
          color: #ef4444;
          background: rgba(239, 68, 68, 0.1);
        }
      }
    }
  }
}

/* Compact role management item. */
.role-card {
  height: 116px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 86%, transparent);
  backdrop-filter: none;
  transition: border-color 160ms ease, background-color 160ms ease;
}

.role-card:hover {
  transform: none;
  box-shadow: none;
  background: var(--bg-card);
}

.role-card.selected {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 1px var(--primary-line);
  background: var(--primary-fade);
}

.card-content { padding: 10px; }
.card-header { gap: 9px; margin-bottom: 6px; }
.card-header .avatar-wrapper {
  width: 34px;
  height: 34px;
  border: 1px solid var(--primary-line);
  border-radius: 7px;
  color: var(--primary-color);
  background: var(--primary-fade);
  box-shadow: none;
  font-size: 14px;
}
.card-header .role-meta .name-row { margin-bottom: 2px; }
.card-header .role-meta .name-row h3 { font-size: 13px; }
.card-header .role-meta .name-row .role-tag { height: 18px; padding: 0 6px; font-size: 9px; }
.card-header .role-meta .name-row .header-right { gap: 5px; }
.card-header .role-meta .name-row .favorite-btn { font-size: 14px; color: var(--text-disabled); }
.card-header .role-meta .role-id { font-size: 9px; }
.card-body .description { font-size: 10px; line-height: 1.4; -webkit-line-clamp: 1; }
.card-footer {
  min-height: 28px;
  margin: 6px -10px -10px;
  padding: 5px 10px;
  background: transparent;
}
.card-footer .status-indicator { gap: 5px; font-size: 10px; }
.card-footer .status-indicator .dot { width: 6px; height: 6px; }
.card-footer .actions { gap: 2px; }
.card-footer .actions .icon-btn { width: 22px; height: 22px; border-radius: 5px; }
</style>
