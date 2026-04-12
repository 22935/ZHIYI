<template>
  <div class="digital-human-container" ref="containerRef">
    <canvas ref="canvasRef" class="digital-human-canvas"></canvas>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-content">
        <div class="loading-spinner">
          <el-icon class="is-loading" :size="40"><Loading /></el-icon>
        </div>
        <span class="loading-text">加载数字人...</span>
        <div class="loading-progress">
          <div class="progress-bar"></div>
        </div>
      </div>
    </div>
    
    <!-- 错误状态 -->
    <div v-if="error && !loading" class="error-overlay">
      <div class="error-content">
        <div class="error-icon">
          <el-icon :size="48"><WarningFilled /></el-icon>
        </div>
        <h3 class="error-title">加载失败</h3>
        <p class="error-message">{{ error }}</p>
        <el-button 
          type="primary" 
          size="small" 
          @click="handleRetry"
          :loading="retrying"
        >
          重试
        </el-button>
      </div>
    </div>
    
    <!-- 空状态 -->
    <div v-if="!props.roleId && !loading && !error" class="empty-overlay">
      <div class="empty-content">
        <div class="empty-icon">
          <el-icon :size="64"><UserFilled /></el-icon>
        </div>
        <h3 class="empty-title">请选择角色</h3>
        <p class="empty-message">选择一个角色以加载数字人</p>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { Loading, WarningFilled, UserFilled } from '@element-plus/icons-vue'
import * as THREE from 'three'
import { digitalHumanApi } from '@/services/api/digitalHuman'
import { ElMessage } from 'element-plus'
import { kylinOSRenderer } from '@/utils/kylinOSRenderer'
import { useRoleStore } from '@/stores/role'

interface Props {
  roleId?: string
  avatarId?: string  // 形象ID（可选，不提供则使用角色的第一个形象）
  isSpeaking?: boolean
  audioUrl?: string
  style?: string
  transparent?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isSpeaking: false,
  style: 'realistic',
  transparent: false
})

const emit = defineEmits(['update:style'])

const containerRef = ref<HTMLElement>()
const canvasRef = ref<HTMLCanvasElement>()
const loading = ref(true)
const error = ref<string>('')
const retrying = ref(false)

let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let animationId: number | null = null
let digitalHumanModel: THREE.Group | null = null
let lipSyncMixer: THREE.AnimationMixer | null = null
let lipSyncAction: THREE.AnimationAction | null = null
let isLipSyncing = false

onMounted(async () => {
  await initThreeJS()
  if (props.roleId) {
    await createDigitalHuman()
  }
})

onUnmounted(() => {
  cleanup()
})

watch(() => props.isSpeaking, (speaking) => {
  if (speaking) {
    startLipSync()
  } else {
    stopLipSync()
  }
})

watch(() => props.roleId, async (newRoleId, oldRoleId) => {
  if (newRoleId && newRoleId !== oldRoleId) {
    // 清除旧模型
    if (digitalHumanModel && scene) {
      scene.remove(digitalHumanModel)
      digitalHumanModel = null
    }
    await loadDigitalHuman()
  }
})

watch(() => props.style, async (newStyle, oldStyle) => {
  if (props.roleId && newStyle && newStyle !== oldStyle) {
    try {
      loading.value = true
      const response = await digitalHumanApi.switchStyle(props.roleId, newStyle)
      if (response.success && response.data) {
        // 重新加载数字人模型或图像
        const modelData = response.data
        // 优先使用2D图像（如果存在）
        // 优先使用avatar字段，如果没有则使用local_image_url或image_url
        // 确保URL是完整的API路径（/ai/digital-human/image/...）
        let imageUrl = modelData.avatar || modelData.local_image_url || modelData.image_url
        if (imageUrl) {
          // 如果URL是静态文件路径（/api/static/...），转换为API路径
          if (imageUrl.includes('/api/static/digital-human')) {
            // 从静态路径提取文件名
            const filename = imageUrl.split('/').pop()
            imageUrl = `/ai/digital-human/image/${filename}`
          } else if (imageUrl.includes('/static/digital-human')) {
            // 处理 /static/digital-human/... 路径
            const filename = imageUrl.split('/').pop()
            imageUrl = `/ai/digital-human/image/${filename}`
          }
          // 确保URL以/开头
          if (!imageUrl.startsWith('/') && !imageUrl.startsWith('http')) {
            imageUrl = '/' + imageUrl
          }
          await load2DImage(imageUrl)
        } else if (modelData.modelUrl) {
          await load3DModel(modelData.modelUrl)
        } else if (modelData.modelPath) {
          await load3DModel(modelData.modelPath)
        } else {
          createPlaceholderModel()
        }
        ElMessage.success('风格切换成功')
      } else {
        ElMessage.warning('风格切换失败，已显示占位符')
        createPlaceholderModel()
      }
    } catch (e: any) {
      ElMessage.warning('风格切换失败: ' + (e.message || '未知错误') + '，已显示占位符')
      createPlaceholderModel()
    } finally {
      loading.value = false
    }
  }
})

const initThreeJS = async () => {
  if (!canvasRef.value || !containerRef.value) return

  try {
    // 创建场景
    scene = new THREE.Scene()
    if (!props.transparent) {
      scene.background = new THREE.Color(0xf5f7fa)
    }

    // 创建相机
    const width = containerRef.value.clientWidth
    const height = containerRef.value.clientHeight
    camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000)
    camera.position.z = 5

    // 创建渲染器（适配银河麒麟系统）
    renderer = kylinOSRenderer.createRenderer(canvasRef.value)
    renderer.setSize(width, height)
    
    // 获取推荐的渲染设置
    const settings = kylinOSRenderer.getRecommendedSettings()
    renderer.setPixelRatio(settings.pixelRatio)

    // 添加光源（使用柔和的白色光源）
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8)
    scene.add(ambientLight)

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.6)
    directionalLight.position.set(5, 5, 5)
    scene.add(directionalLight)

    // 不创建任何占位符，场景保持空白，等待加载实际数字人图像
    // 这样避免显示蓝色方块或其他占位符

    // 开始渲染循环
    animate()

    loading.value = false
  } catch (e: any) {
    error.value = '初始化数字人失败: ' + e.message
    loading.value = false
  }
}

/**
 * 创建数字人
 */
/**
 * 加载数字人（自动检测是否已存在，如果不存在则创建）
 */
const loadDigitalHuman = async () => {
  if (!props.roleId) {
    error.value = '角色ID不能为空'
    return
  }

  try {
    loading.value = true
    error.value = ''
    
    // 确保Three.js已初始化
    if (!scene || !camera || !renderer) {
      await initThreeJS()
    }
    
    // 先尝试获取已存在的数字人
    let modelData = null
    try {
      const getResponse = await digitalHumanApi.getDigitalHuman(props.roleId, props.avatarId)
      // 检查响应是否成功
      if (getResponse && getResponse.success && getResponse.data) {
        modelData = getResponse.data
        console.log('加载已存在的数字人:', modelData)
      } else if (getResponse && !getResponse.success) {
        // 如果返回了响应但 success 为 false（比如 404），尝试创建新的
        console.log('数字人不存在，创建新的数字人')
        const createResponse = await digitalHumanApi.createDigitalHuman({
          roleId: props.roleId,
          style: props.style || 'realistic'
        })
        if (createResponse && createResponse.success) {
          modelData = createResponse.data
          console.log('✅ 数字人创建成功:', modelData)
          console.log('📦 数据字段:', Object.keys(modelData))
        }
      }
    } catch (e: any) {
      // 如果数字人不存在（404），则创建新的
      // 检查多种可能的错误格式
      const is404 = e.response?.status === 404 || 
                    e.status === 404 || 
                    (e.response?.data && e.response.data.success === false && e.response.data.message?.includes('不存在'))
      
      if (is404) {
        console.log('数字人不存在，创建新的数字人')
        try {
          const createResponse = await digitalHumanApi.createDigitalHuman({
            roleId: props.roleId,
            style: props.style || 'realistic'
          })
          if (createResponse && createResponse.success) {
        modelData = createResponse.data
        console.log('✅ 数字人创建成功:', modelData)
        console.log('📦 数据字段:', Object.keys(modelData || {}))
            // 更新角色头像
            const avatarUrl = modelData.avatar || modelData.local_image_url
            if (avatarUrl && props.roleId) {
              const roleStore = useRoleStore()
              roleStore.updateRoleAvatar(props.roleId, avatarUrl)
            }
          }
        } catch (createError: any) {
          console.error('创建数字人失败:', createError)
          // 如果创建也失败，继续使用占位符，不抛出错误
        }
      } else {
        // 其他错误直接抛出
        throw e
      }
    }
    
    // 如果获取或创建成功，加载模型或图像
    if (modelData) {
      console.log('📦 数字人数据:', JSON.stringify(modelData, null, 2))
      
      // 优先使用2D图像（如果存在）
      const imageUrl = modelData.avatar || modelData.local_image_url || modelData.image_url
      console.log('🖼️ 图像URL检查:', {
        avatar: modelData.avatar,
        local_image_url: modelData.local_image_url,
        image_url: modelData.image_url,
        selected: imageUrl,
        avatar_id: modelData.avatar_id,
        role_id: modelData.role_id
      })
      
      if (imageUrl) {
        // 确保URL是完整的（如果是相对路径，使用相对路径，Vite代理会处理）
        let fullImageUrl = imageUrl
        if (!imageUrl.startsWith('http')) {
          // 如果不是完整URL，确保是相对路径（以/开头）
          if (!imageUrl.startsWith('/')) {
            fullImageUrl = '/' + imageUrl
          }
          // 相对路径会被Vite代理处理，不需要添加window.location.origin
          // /ai 路径会被代理到 http://localhost:8080/ai
          // /api 路径会被代理到 http://localhost:8080/api
        }
        console.log('🖼️ 完整图像URL:', fullImageUrl)
        await load2DImage(fullImageUrl)
      } else if (modelData.modelUrl) {
        // 如果没有图像，尝试加载3D模型
        console.log('📦 尝试加载3D模型:', modelData.modelUrl)
        await load3DModel(modelData.modelUrl)
      } else if (modelData.modelPath) {
        console.log('📦 尝试加载3D模型路径:', modelData.modelPath)
        await load3DModel(modelData.modelPath)
      } else {
        // 如果都没有，使用占位符
        console.warn('⚠️ 没有找到图像或模型，使用占位符')
        createPlaceholderModel()
      }
      
      ElMessage.success('数字人加载成功')
      loading.value = false
    } else {
      console.error('❌ 无法获取数字人数据')
      throw new Error('无法获取数字人数据')
    }
  } catch (e: any) {
    let errorMsg = '加载数字人失败'
    
    if (e.response && e.response.data) {
      const errorData = e.response.data
      errorMsg = errorData.message || errorData.error || errorData.msg || errorMsg
    } else if (e.message) {
      errorMsg = e.message
    } else if (typeof e === 'string') {
      errorMsg = e
    }
    
    error.value = errorMsg
    
    // 即使加载失败，也显示占位符
    if (!scene || !camera || !renderer) {
      await initThreeJS()
    }
    createPlaceholderModel()
    
    // 更友好的错误提示
    if (e.response?.status === 500) {
      ElMessage.warning({
        message: '数字人服务暂时不可用，已显示占位符',
        duration: 3000
      })
    } else if (e.response?.status === 404) {
      ElMessage.warning('数字人服务未找到，已显示占位符')
    } else {
      ElMessage.warning(errorMsg + '，已显示占位符')
    }
    
    loading.value = false
  }
}

/**
 * 创建数字人（兼容旧接口，实际调用loadDigitalHuman）
 */
const createDigitalHuman = async () => {
  await loadDigitalHuman()
}

// 使用 let 而不是 const，以便在需要时重新赋值
let animate = () => {
  if (!scene || !camera || !renderer) return

  // 移除旋转动画，保持静态显示
  // 如果需要动画效果，可以在特定场景下添加（如说话时的口型同步）

  animationId = requestAnimationFrame(animate)
  renderer.render(scene, camera)
}

/**
 * 加载3D模型
 */
const load3DModel = async (modelUrl: string) => {
  if (!scene) return
  
  try {
    // 清除旧模型
    if (digitalHumanModel) {
      scene.remove(digitalHumanModel)
      digitalHumanModel = null
    }
    
    // 这里应该使用GLTFLoader加载模型
    // 由于需要额外安装@react-three/gltfjsx或three/examples/jsm/loaders/GLTFLoader
    // 暂时使用占位符，实际项目中应该加载真实的3D模型
    createPlaceholderModel()
    
    // 实际实现示例（需要安装three/examples/jsm/loaders/GLTFLoader）:
    // import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader'
    // const loader = new GLTFLoader()
    // const gltf = await loader.loadAsync(modelUrl)
    // digitalHumanModel = gltf.scene
    // scene.add(digitalHumanModel)
    // 
    // // 设置动画混合器
    // if (gltf.animations && gltf.animations.length > 0) {
    //   lipSyncMixer = new THREE.AnimationMixer(digitalHumanModel)
    // }
  } catch (e: any) {
    console.error('加载3D模型失败:', e)
    createPlaceholderModel()
  }
}

/**
 * 加载2D图像（作为纹理应用到平面）
 */
const load2DImage = async (imageUrl: string) => {
  if (!scene) {
    console.error('❌ 场景未初始化，无法加载图像')
    return
  }
  
  console.log('🖼️ 开始加载2D图像:', imageUrl)
  
  try {
    // 清除旧模型和所有占位符
    if (digitalHumanModel) {
      scene.remove(digitalHumanModel)
      digitalHumanModel = null
    }
    
    // 清除场景中所有其他Mesh对象（确保没有残留的占位符或蓝色方块）
    const objectsToRemove: THREE.Object3D[] = []
    scene.traverse((object) => {
      // 移除所有Mesh对象（除了光源和相机）
      if (object instanceof THREE.Mesh) {
        objectsToRemove.push(object)
      }
    })
    objectsToRemove.forEach(obj => {
      if (obj.parent) {
        obj.parent.remove(obj)
      }
      // 清理资源
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose()
        if (Array.isArray(obj.material)) {
          obj.material.forEach(mat => mat.dispose())
        } else {
          obj.material.dispose()
        }
      }
    })
    
    console.log('🧹 已清除所有旧对象，准备加载新图像')
    
    // 创建纹理加载器
    const textureLoader = new THREE.TextureLoader()
    
    // 设置跨域（如果需要）
    textureLoader.setCrossOrigin('anonymous')
    
    // 加载图像纹理
    const texture = await new Promise<THREE.Texture>((resolve, reject) => {
      console.log('📥 开始加载纹理:', imageUrl)
      
      textureLoader.load(
        imageUrl,
        (texture) => {
          console.log('✅ 纹理加载成功:', {
            width: texture.image.width,
            height: texture.image.height,
            url: imageUrl
          })
          
          // 设置纹理参数
          texture.flipY = false
          texture.minFilter = THREE.LinearFilter
          texture.magFilter = THREE.LinearFilter
          texture.needsUpdate = true
          resolve(texture)
        },
        (progress) => {
          // 加载进度
          if (progress.total > 0) {
            const percent = (progress.loaded / progress.total) * 100
            console.log(`📊 图像加载进度: ${percent.toFixed(1)}%`)
          }
        },
        (error) => {
          console.error('❌ 加载图像纹理失败:', {
            error,
            url: imageUrl,
            message: error?.message || '未知错误'
          })
          reject(error)
        }
      )
    })
    
    // 获取容器尺寸
    const containerWidth = containerRef.value?.clientWidth || 1
    const containerHeight = containerRef.value?.clientHeight || 1
    const containerAspect = containerWidth / containerHeight
    
    // 获取图像尺寸和比例
    const imageWidth = texture.image.width
    const imageHeight = texture.image.height
    const imageAspect = imageWidth / imageHeight
    
    console.log('📐 容器和图像尺寸:', {
      container: { width: containerWidth, height: containerHeight, aspect: containerAspect },
      image: { width: imageWidth, height: imageHeight, aspect: imageAspect }
    })
    
    // 计算缩放以填满容器，同时保持图像比例
    let planeWidth: number
    let planeHeight: number
    
    if (imageAspect > containerAspect) {
      // 图像更宽，以宽度为准
      planeWidth = 3
      planeHeight = 3 / imageAspect
    } else {
      // 图像更高，以高度为准
      planeHeight = 3
      planeWidth = 3 * imageAspect
    }
    
    const geometry = new THREE.PlaneGeometry(planeWidth, planeHeight)
    
    console.log('📐 创建平面几何体:', { width: planeWidth, height: planeHeight })
    
    // 创建材质
    const material = new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      side: THREE.DoubleSide
    })
    
    // 创建网格
    digitalHumanModel = new THREE.Group()
    const plane = new THREE.Mesh(geometry, material)
    // 旋转图像180度（绕Y轴和Z轴旋转）
    plane.rotation.y = Math.PI
    plane.rotation.z = Math.PI
    digitalHumanModel.add(plane)
    
    // 添加到场景
    scene.add(digitalHumanModel)
    
    console.log('✅ 图像网格已添加到场景')
    
    // 调整相机位置以适应图像，确保图像填满视口
    if (camera) {
      // 计算相机距离，使图像填满视口
      const fov = camera.fov * (Math.PI / 180)
      const distance = Math.max(
        planeHeight / (2 * Math.tan(fov / 2)),
        planeWidth / (2 * Math.tan(fov / 2) * containerAspect)
      ) * 1.1 // 稍微远一点，确保完全可见
      
      camera.position.z = distance
      camera.lookAt(0, 0, 0)
      camera.updateProjectionMatrix()
      console.log('📷 相机位置已调整:', { z: distance, fov: camera.fov })
    }
    
    console.log('✅ 2D图像加载并显示成功:', imageUrl)
  } catch (e: any) {
    console.error('❌ 加载2D图像失败:', {
      error: e,
      message: e?.message,
      url: imageUrl,
      stack: e?.stack
    })
    
    // 尝试使用img标签预加载，检查图像是否可访问
    const img = new Image()
    img.onload = () => {
      console.log('✅ 图像可以访问，但Three.js加载失败，可能是CORS问题')
    }
    img.onerror = (err) => {
      console.error('❌ 图像无法访问:', {
        url: imageUrl,
        error: err
      })
    }
    img.src = imageUrl
    
    // 如果加载失败，使用占位符
    console.warn('⚠️ 使用占位符替代')
    createPlaceholderModel()
  }
}

/**
 * 创建占位符模型
 */
const createPlaceholderModel = () => {
  if (!scene) return
  
  // 清除旧模型
  if (digitalHumanModel) {
    scene.remove(digitalHumanModel)
    digitalHumanModel = null
  }
  
  // 创建一个简洁的灰色占位符（不使用蓝色，不使用复杂形状）
  const group = new THREE.Group()
  
  // 简单的灰色平面作为占位符
  const placeholderGeometry = new THREE.PlaneGeometry(2, 3)
  const placeholderMaterial = new THREE.MeshBasicMaterial({ 
    color: 0xe0e0e0,  // 浅灰色
    transparent: true,
    opacity: 0.5
  })
  const placeholder = new THREE.Mesh(placeholderGeometry, placeholderMaterial)
  // 旋转占位符180度（与图像保持一致）
  placeholder.rotation.y = Math.PI
  placeholder.rotation.z = Math.PI
  group.add(placeholder)
  
  // 不添加任何动画，保持完全静态
  
  digitalHumanModel = group
  scene.add(digitalHumanModel)
}

const startLipSync = async () => {
  if (!props.roleId || !props.audioUrl) return
  
  isLipSyncing = true

  try {
    // 获取音频文件
    const audioResponse = await fetch(props.audioUrl)
    const audioBlob = await audioResponse.blob()
    const audioFile = new File([audioBlob], 'audio.wav', { type: 'audio/wav' })

    // 调用后端API更新动画
    const response = await digitalHumanApi.updateAnimation(
      props.roleId,
      '', // text可以从props获取
      audioFile
    )

    if (response.success) {
      // 使用返回的动画数据更新3D模型
      const animationData = response.data
      if (animationData?.animationUrl && lipSyncMixer) {
        // 加载动画并播放
        // 实际实现需要加载动画文件
        console.log('口型同步开始，动画URL:', animationData.animationUrl)
        
        // 简单的口型同步效果：缩放头部
        if (digitalHumanModel) {
          const head = digitalHumanModel.children.find(child => child.position.y > 1)
          if (head) {
            const scaleAnimation = () => {
              if (isLipSyncing && head) {
                const scale = 1 + Math.sin(Date.now() * 0.01) * 0.1
                head.scale.set(scale, scale, scale)
              }
            }
            const interval = setInterval(() => {
              if (!isLipSyncing) {
                clearInterval(interval)
                if (head) head.scale.set(1, 1, 1)
              } else {
                scaleAnimation()
              }
            }, 50)
          }
        }
      } else {
        console.log('口型同步开始（无动画数据）')
      }
    }
  } catch (e: any) {
    console.error('口型同步失败:', e)
    isLipSyncing = false
  }
}

const stopLipSync = () => {
  isLipSyncing = false
  
  // 停止动画
  if (lipSyncAction) {
    lipSyncAction.stop()
    lipSyncAction = null
  }
  
  // 重置模型状态
  if (digitalHumanModel) {
    const head = digitalHumanModel.children.find(child => child.position.y > 1)
    if (head) {
      head.scale.set(1, 1, 1)
    }
  }
  
  console.log('停止口型同步')
}

const cleanup = () => {
  if (animationId) {
    cancelAnimationFrame(animationId)
  }
  if (renderer) {
    renderer.dispose()
  }
  if (lipSyncMixer) {
    lipSyncMixer.stopAllAction()
    lipSyncMixer = null
  }
  if (digitalHumanModel && scene) {
    scene.remove(digitalHumanModel)
    digitalHumanModel = null
  }
  scene = null
  camera = null
  renderer = null
  isLipSyncing = false
}

// 响应窗口大小变化
const handleResize = () => {
  if (!containerRef.value || !camera || !renderer) return

  const width = containerRef.value.clientWidth
  const height = containerRef.value.clientHeight

  camera.aspect = width / height
  camera.updateProjectionMatrix()
  renderer.setSize(width, height)
  
  // 如果已有数字人模型，重新调整相机位置以适应新尺寸
  if (digitalHumanModel && scene) {
    const plane = digitalHumanModel.children[0] as THREE.Mesh
    if (plane && plane.geometry instanceof THREE.PlaneGeometry) {
      const planeWidth = plane.geometry.parameters.width
      const planeHeight = plane.geometry.parameters.height
      const containerAspect = width / height
      
      const fov = camera.fov * (Math.PI / 180)
      const distance = Math.max(
        planeHeight / (2 * Math.tan(fov / 2)),
        planeWidth / (2 * Math.tan(fov / 2) * containerAspect)
      ) * 1.1
      
      camera.position.z = distance
      camera.lookAt(0, 0, 0)
      camera.updateProjectionMatrix()
    }
  }
}

const handleRetry = async () => {
  if (!props.roleId) {
    ElMessage.warning('请先选择角色')
    return
  }
  
  retrying.value = true
  error.value = ''
  await loadDigitalHuman()
  retrying.value = false
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped lang="scss">
.digital-human-container {
  width: 100%;
  height: 100%;
  position: relative;
  /* background removed to support transparency */
  border-radius: var(--border-radius-large);
  overflow: hidden;
  /* border removed to support transparency */
}

.digital-human-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.loading-overlay,
.error-overlay,
.empty-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.2); /* Semi-transparent default */
  backdrop-filter: blur(8px);
  z-index: 10;
}

.loading-content, .error-content, .empty-content {
  background: rgba(255, 255, 255, 0.8);
  padding: 24px;
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  text-align: center;
}

/* Dark mode / transparent mode adaptation could be added here if needed */

.loading-spinner {
  position: relative;
  
  .is-loading {
    animation: rotate 1s linear infinite;
    color: #409eff;
  }
}

.loading-text {
  font-size: 16px;
  font-weight: 500;
  color: #606266;
}

.loading-progress {
  width: 200px;
  height: 4px;
  background: #e4e7ed;
  border-radius: 2px;
  overflow: hidden;
  position: relative;
}

.progress-bar {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 30%;
  background: var(--primary-color);
  border-radius: 2px;
  animation: progress 1.5s ease-in-out infinite;
}

/* 设置面板已移至右侧面板，相关样式已移除 */

@keyframes progress {
  0% {
    left: -30%;
  }
  100% {
    left: 100%;
  }
}

.error-content,
.empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  text-align: center;
  padding: 32px;
  max-width: 300px;
}

.error-icon,
.empty-icon {
  color: #f56c6c;
  opacity: 0.8;
}

.empty-icon {
  color: #909399;
}

.error-title,
.empty-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.error-message,
.empty-message {
  margin: 0;
  font-size: 14px;
  color: #909399;
  line-height: 1.6;
}

.is-loading {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>

