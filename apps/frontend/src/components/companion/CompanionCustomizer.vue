<template>
  <section class="diy" data-testid="companion-customizer" aria-label="形象工坊">
    <header class="diy-head">
      <span>形象工坊 · 随改随看</span>
      <button type="button" data-testid="companion-diy-close" @click="emit('close')">收起</button>
    </header>

    <div class="diy-row">
      <label class="diy-label" for="diy-name">名字</label>
      <input
        id="diy-name"
        v-model="draft.name"
        class="diy-input"
        type="text"
        maxlength="12"
        data-testid="companion-diy-name"
      />
    </div>

    <div class="diy-row">
      <label class="diy-label" for="diy-shape">轮廓</label>
      <select id="diy-shape" v-model="draft.shape" class="diy-input" data-testid="companion-diy-shape">
        <option v-for="(label, shape) in SHAPE_LABEL" :key="shape" :value="shape">{{ label }}</option>
      </select>
    </div>

    <div class="diy-colors">
      <label class="diy-color">
        <span>主色</span>
        <input v-model="draft.primary" type="color" data-testid="companion-diy-primary" />
      </label>
      <label class="diy-color">
        <span>点缀</span>
        <input v-model="draft.accent" type="color" data-testid="companion-diy-accent" />
      </label>
      <label class="diy-color">
        <span>底色</span>
        <input v-model="draft.background" type="color" data-testid="companion-diy-background" />
      </label>
    </div>

    <div class="diy-presets" data-testid="companion-diy-presets">
      <button
        v-for="preset in DIY_PRESETS"
        :key="preset.id"
        type="button"
        :data-testid="`companion-diy-preset-${preset.id}`"
        :style="{ '--swatch': preset.value.primary }"
        @click="applyPreset(preset)"
      >{{ preset.label }}</button>
    </div>

    <div class="diy-row diy-row--file">
      <label class="diy-label">头像图</label>
      <div class="diy-file">
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          data-testid="companion-diy-image"
          @change="onFile"
        />
        <button v-if="draft.image" type="button" data-testid="companion-diy-clear-image" @click="clearImage">清除图片</button>
      </div>
    </div>
    <p v-if="imageHint" class="diy-hint" data-testid="companion-diy-image-hint">{{ imageHint }}</p>

    <div class="diy-row diy-row--stack">
      <label class="diy-label" for="diy-lines">专属台词<small>每行一句，留空用默认</small></label>
      <textarea
        id="diy-lines"
        v-model="linesText"
        class="diy-input"
        rows="3"
        placeholder="今天也想和你一起慢慢来"
        data-testid="companion-diy-lines"
      ></textarea>
    </div>

    <div class="diy-sliders">
      <label>语速 <input v-model.number="draft.voice.rate" type="range" min="0.5" max="2" step="0.05" data-testid="companion-diy-rate" /></label>
      <label>音调 <input v-model.number="draft.voice.pitch" type="range" min="0" max="2" step="0.05" data-testid="companion-diy-pitch" /></label>
      <label>音量 <input v-model.number="draft.voice.volume" type="range" min="0" max="1" step="0.05" data-testid="companion-diy-volume" /></label>
    </div>

    <label class="diy-check">
      <input v-model="draft.motion" type="checkbox" data-testid="companion-diy-motion" />
      眨眼 / 说话口型动效
    </label>

    <details class="diy-share">
      <summary>导出 / 导入形象</summary>
      <textarea
        v-model="shareText"
        class="diy-input"
        rows="3"
        placeholder="把导出的 JSON 贴进来，或复制走分享给别人"
        data-testid="companion-diy-share"
      ></textarea>
      <div class="diy-share-actions">
        <button type="button" data-testid="companion-diy-export" @click="doExport">导出</button>
        <button type="button" data-testid="companion-diy-import" @click="doImport">导入</button>
      </div>
    </details>

    <footer class="diy-foot">
      <button type="button" data-testid="companion-diy-reset" @click="doReset">恢复默认</button>
      <button type="button" class="diy-save" data-testid="companion-diy-save" @click="doSave">保存形象</button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
// 注意：这里刻意不 watch props.value。工坊打开时会以当前配置初始化 draft，
// 之后 draft 的每次改动都会 emit('preview') 让父级更新 customization；
// 若再回写 draft 就会形成「预览 → 同步 → 预览」的无限循环。

import {
  DEFAULT_CUSTOMIZATION, DIY_PRESETS, MAX_IMAGE_CHARS, SHAPE_LABEL,
  exportCustomization, importCustomization, parseLines, sanitizeCustomization,
  type DiyPreset
} from '@/features/companion/customization'
import type { CompanionCustomization, DiyShape } from '@/features/companion/types'

const props = defineProps<{ value: CompanionCustomization }>()
const emit = defineEmits<{
  (event: 'preview', value: CompanionCustomization): void
  (event: 'apply', value: CompanionCustomization): void
  (event: 'close'): void
}>()

const clone = (value: CompanionCustomization): CompanionCustomization => ({
  ...value,
  voice: { ...value.voice },
  lines: [...value.lines]
})

const draft = ref<CompanionCustomization>(clone(props.value))
const linesText = ref(props.value.lines.join('\n'))
const shareText = ref('')
const imageHint = ref('')

const current = (): CompanionCustomization => sanitizeCustomization({
  ...draft.value,
  voice: { ...draft.value.voice },
  lines: parseLines(linesText.value)
})

// 实时预览：拖颜色、换轮廓时立刻重建渲染器，不用等点保存。
watch(draft, () => emit('preview', current()), { deep: true })
watch(linesText, () => emit('preview', current()))

const applyPreset = (preset: DiyPreset): void => {
  draft.value = {
    ...draft.value,
    shape: preset.value.shape as DiyShape,
    primary: preset.value.primary,
    accent: preset.value.accent,
    background: preset.value.background
  }
}

const clearImage = (): void => {
  draft.value.image = null
  imageHint.value = '已换回矢量小脸。'
}

const onFile = (event: Event): void => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  imageHint.value = ''
  if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) {
    imageHint.value = '只支持 PNG / JPG / WebP / GIF。'
    return
  }
  if (file.size > 4 * 1024 * 1024) {
    imageHint.value = '原图请不要超过 4MB。'
    return
  }
  const reader = new FileReader()
  reader.onerror = () => { imageHint.value = '图片读取失败，换一张试试。' }
  reader.onload = () => {
    const source = String(reader.result || '')
    const image = new Image()
    image.onerror = () => { imageHint.value = '这张图打不开，换一张试试。' }
    image.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = 256
        canvas.height = 256
        const context = canvas.getContext('2d')
        if (!context) { imageHint.value = '当前环境不能处理图片，请换用矢量形象。'; return }
        context.drawImage(image, 0, 0, 256, 256)
        const dataUrl = canvas.toDataURL('image/png')
        if (dataUrl.length > MAX_IMAGE_CHARS) {
          imageHint.value = '压缩后还是太大，换张简单点的图吧。'
          return
        }
        draft.value.image = dataUrl
        imageHint.value = '换好啦，图片只保存在这台设备上。'
      } catch {
        imageHint.value = '当前环境不能处理图片，请换用矢量形象。'
      }
    }
    image.src = source
  }
  reader.readAsDataURL(file)
}

const doExport = (): void => {
  shareText.value = exportCustomization(current())
  imageHint.value = '已生成形象 JSON，复制走就能分享。'
}

const doImport = (): void => {
  const imported = importCustomization(shareText.value)
  if (!imported) { imageHint.value = '这段 JSON 读不出来，检查后重试。'; return }
  draft.value = clone(imported)
  linesText.value = imported.lines.join('\n')
  imageHint.value = '导入成功，记得点保存形象。'
}

const doReset = (): void => {
  draft.value = clone(DEFAULT_CUSTOMIZATION)
  linesText.value = ''
  imageHint.value = '已恢复默认，记得点保存形象。'
}

const doSave = (): void => {
  emit('apply', current())
  emit('close')
}
</script>

<style scoped>
.diy {
  display: flex; flex-direction: column; gap: 7px;
  padding: 9px; border-radius: 9px;
  background: var(--bg-input, var(--bg-app));
  border: 1px solid var(--primary-line, rgba(76, 141, 255, 0.35));
  /* 工坊内容比养成面板长：自己滚动，避免整块浮层被顶到视口外，
     同时让 sticky 的保存栏始终有可滚的祖先容器。 */
  max-height: 330px; overflow-y: auto; overscroll-behavior: contain;
}
.diy-head { display: flex; align-items: center; justify-content: space-between; font-size: 12px; font-weight: 500; }
.diy-head button, .diy-foot button, .diy-share-actions button, .diy-file button, .diy-presets button {
  font: inherit; font-size: 11px; padding: 3px 7px; cursor: pointer;
  color: var(--text-regular, var(--text-primary)); background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px;
}
.diy-row { display: flex; align-items: center; gap: 7px; }
.diy-row--stack { flex-direction: column; align-items: stretch; gap: 4px; }
.diy-label { font-size: 11px; min-width: 48px; color: var(--text-muted, var(--text-secondary)); }
.diy-label small { display: block; font-size: 10px; opacity: 0.8; }
.diy-input {
  flex: 1; min-width: 0; width: 100%; box-sizing: border-box;
  font: inherit; font-size: 11px; padding: 4px 6px; resize: vertical;
  color: var(--text-primary); background: var(--bg-card);
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px;
}
.diy-colors { display: flex; gap: 6px; }
.diy-color { flex: 1; display: flex; align-items: center; gap: 4px; font-size: 10px; color: var(--text-muted, var(--text-secondary)); }
.diy-color input { width: 100%; min-width: 0; height: 22px; padding: 0; border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 5px; background: none; cursor: pointer; }
.diy-presets { display: flex; flex-wrap: wrap; gap: 4px; }
.diy-presets button { display: flex; align-items: center; gap: 4px; }
.diy-presets button::before {
  content: ''; width: 8px; height: 8px; border-radius: 50%; background: var(--swatch);
}
.diy-file { flex: 1; display: flex; align-items: center; gap: 6px; min-width: 0; }
.diy-file input[type="file"] { flex: 1; min-width: 0; font-size: 10px; color: var(--text-muted, var(--text-secondary)); }
.diy-sliders { display: flex; flex-direction: column; gap: 2px; }
.diy-sliders label { display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--text-muted, var(--text-secondary)); }
.diy-sliders input { flex: 1; min-width: 0; }
.diy-check { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
.diy-check input { margin: 0; }
.diy-hint { margin: 0; font-size: 10px; line-height: 1.5; color: var(--primary-color, #4c8dff); }
.diy-share summary { font-size: 11px; cursor: pointer; color: var(--text-muted, var(--text-secondary)); }
.diy-share textarea { margin-top: 5px; }
.diy-share-actions { display: flex; gap: 5px; margin-top: 4px; }
.diy-foot {
  display: flex; justify-content: space-between; gap: 6px;
  position: sticky; bottom: -9px; z-index: 1;
  padding: 7px 0 2px;
  background: var(--bg-input, var(--bg-app));
  border-top: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.22));
}
.diy-save { color: #fff !important; background: var(--primary-color, #4c8dff) !important; border-color: transparent !important; }
</style>
