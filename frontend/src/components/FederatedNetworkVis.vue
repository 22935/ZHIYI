<!-- 联邦网络拓扑可视化组件 — 星空、能量场、神经线程和中心节点的动效空间可视化 -->
<template>
  <div class="federated-network-vis" :class="theme" ref="container">
    <!-- 极深邃背景 -->
    <div class="spatial-bg">
      <div class="light-pillar lp-1"></div>
      <div class="light-pillar lp-2"></div>
      <div class="star-field">
        <div v-for="i in 50" :key="i" class="star" :style="getStarStyle(i)"></div>
      </div>
    </div>

    <!-- 动态神经中枢可视化 -->
    <div class="neural-nexus">
      <!-- 能量场 -->
      <div class="energy-field">
        <div class="halo h-1"></div>
        <div class="halo h-2"></div>
      </div>

      <!-- 核心枢纽：三维几何构型 -->
      <div class="nexus-core-wrap">
        <div class="nexus-core">
          <div class="core-box cb-1"></div>
          <div class="core-box cb-2"></div>
          <div class="core-box cb-3"></div>
          <div class="inner-glow"></div>
        </div>
        
      </div>

      <!-- 神经连接系统 -->
      <div class="neural-threads">
        <div 
          v-for="i in 12" 
          :key="i" 
          class="thread-unit"
          :style="getThreadStyle(i)"
        >
          <div class="thread-line"></div>
          <div class="thread-particle"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps({
  theme: {
    type: String,
    default: 'dark'
  }
})

const getStarStyle = (i: number) => ({
  top: `${Math.random() * 100}%`,
  left: `${Math.random() * 100}%`,
  opacity: Math.random() * 0.5 + 0.2,
  animationDelay: `${Math.random() * 5}s`
})

const getThreadStyle = (i: number) => {
  const angle = ((i - 1) / 12) * 360
  const dist = 240 + (i % 3) * 30
  return {
    transform: `rotate(${angle}deg)`,
    '--dist': `${dist}px`,
    '--delay': `${i * 0.5}s`,
    '--angle': `${angle}deg`
  }
}
</script>

<style scoped lang="scss">
.federated-network-vis {
  --nexus-color: var(--primary-color);
  --nexus-glow: rgba(99, 102, 241, 0.4);
  --node-color: #10b981;
  --bg-spatial: radial-gradient(circle at center, #0d111a 0%, #05070a 100%);
  --glass-heavy: rgba(255, 255, 255, 0.05);
  
  &.light {
    --nexus-color: var(--primary-color);
    --nexus-glow: rgba(79, 70, 229, 0.15);
    --node-color: #059669;
    --bg-spatial: linear-gradient(135deg, #f0f4ff 0%, #fcfdfe 50%, #f5f7ff 100%);
    --glass-heavy: rgba(255, 255, 255, 0.9);
  }

  position: relative;
  width: 100%;
  height: 600px;
  background: var(--bg-spatial);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition: all 1s cubic-bezier(0.4, 0, 0.2, 1);
}

/* --- 空间背景渲染 --- */
.spatial-bg {
  position: absolute;
  inset: 0;
  z-index: 1;
  
  .light-pillar {
    position: absolute;
    width: 60%;
    height: 140%;
    background: radial-gradient(ellipse at center, var(--nexus-glow) 0%, transparent 75%);
    opacity: 0.15;
    filter: blur(100px);
  }
  .lp-1 { top: -30%; left: -15%; transform: rotate(-25deg); }
  .lp-2 { bottom: -30%; right: -15%; transform: rotate(-25deg); }

  /* 增加一个动态星云层 */
  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background: 
      radial-gradient(circle at 20% 30%, rgba(99, 102, 241, 0.05) 0%, transparent 40%),
      radial-gradient(circle at 80% 70%, rgba(16, 185, 129, 0.03) 0%, transparent 40%);
    filter: blur(40px);
    animation: nebula-float 15s infinite alternate ease-in-out;
  }

  .star-field {
    position: absolute;
    inset: 0;
    .star {
      position: absolute;
      width: 1px;
      height: 1px;
      background: white;
      border-radius: 50%;
      animation: twinkle 3s infinite ease-in-out;
    }
  }
}

@keyframes nebula-float {
  from { transform: scale(1) translate(0, 0); }
  to { transform: scale(1.1) translate(20px, 10px); }
}

.neural-nexus {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* --- 中心核心：三维构件 --- */
.nexus-core-wrap {
  position: relative;
  width: 320px;
  height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nexus-core {
  position: relative;
  width: 200px;
  height: 200px;
  transform-style: preserve-3d;
  animation: core-rotate 25s linear infinite;

  .core-box {
    position: absolute;
    inset: 0;
    border: 4px solid var(--nexus-color);
    border-radius: 40px;
    opacity: 0.4;
    background: transparent;
    transition: all 0.5s ease;
  }
  .cb-1 { transform: rotateX(45deg) rotateY(45deg); }
  .cb-2 { transform: rotateX(-45deg) rotateY(45deg); }
  .cb-3 { transform: rotateY(90deg); }

  .inner-glow {
    position: absolute;
    inset: 20%;
    background: var(--nexus-color);
    border-radius: 50%;
    filter: blur(45px);
    opacity: 0.6;
    animation: core-pulse 4s infinite ease-in-out;
  }
}

.core-tag {
  position: absolute;
  top: 110%;
  text-align: center;
  white-space: nowrap;
  
  .tag-title {
    font-size: 18px;
    font-weight: 900;
    letter-spacing: 8px;
    color: var(--nexus-color);
    margin-bottom: 16px;
    opacity: 0.95;
  }
  .tag-status {
    font-size: 14px;
    font-weight: 800;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 32px;
    background: var(--glass-heavy);
    backdrop-filter: blur(15px);
    border: 1px solid var(--border);
    border-radius: 50px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.15);

    .pulse-dot {
      width: 8px;
      height: 8px;
      background: var(--node-color);
      border-radius: 50%;
      box-shadow: 0 0 20px var(--node-color);
      animation: status-pulse 2s infinite;
    }
  }
}

/* --- 神经连接连线 --- */
.neural-threads {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thread-unit {
  position: absolute;
  width: var(--dist);
  height: 1px;
  transform-origin: 0 50%;
  left: 50%;
  
  .thread-line {
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, var(--nexus-color) 0%, transparent 100%);
    opacity: 0.15;
  }

  .thread-particle {
    position: absolute;
    width: 30px;
    height: 1px;
    background: linear-gradient(90deg, transparent, white, transparent);
    animation: flow-run 4s infinite linear;
    animation-delay: var(--delay);
    filter: blur(1px);
  }

  .node-endpoint {
    position: absolute;
    right: 0;
    top: 50%;
    transform: translate(50%, -50%) rotate(calc(-1 * var(--angle)));
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;

    .endpoint-dot {
      width: 6px;
      height: 6px;
      background: var(--node-color);
      border-radius: 50%;
      box-shadow: 0 0 12px var(--node-color);
    }
    .endpoint-info {
      font-size: 10px;
      font-weight: 800;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-bright);
      opacity: 0.6;
      background: var(--glass-heavy);
      padding: 2px 8px;
      border-radius: 4px;
      margin-top: 4px;
      white-space: nowrap;
    }
  }
}

/* --- 核心动画 --- */
@keyframes core-rotate {
  from { transform: rotateX(0deg) rotateY(0deg) rotateZ(0deg); }
  to { transform: rotateX(360deg) rotateY(360deg) rotateZ(360deg); }
}

@keyframes core-pulse {
  0%, 100% { transform: scale(1); opacity: 0.4; }
  50% { transform: scale(1.3); opacity: 0.6; }
}

@keyframes flow-run {
  0% { left: 0%; opacity: 0; }
  20% { opacity: 1; }
  80% { opacity: 1; }
  100% { left: 100%; opacity: 0; }
}

@keyframes status-pulse {
  0% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.5); }
  100% { opacity: 1; transform: scale(1); }
}

@keyframes twinkle {
  0%, 100% { opacity: 0.2; }
  50% { opacity: 0.8; }
}
</style>
