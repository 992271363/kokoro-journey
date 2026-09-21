<template>
  <div class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Settings</p>
        <h1 class="page-title">设置</h1>
      </div>
    </header>

    <p v-if="message" class="flash" :class="messageType">
      <i
        class="fas"
        :class="messageType === 'ok' ? 'fa-circle-check' : 'fa-triangle-exclamation'"
      ></i>
      {{ message }}
    </p>

    <section class="panel">
      <div class="panel-header">
        <h2 class="panel-title">背景</h2>
        <span class="panel-badge">当前：{{ currentLabel }}</span>
      </div>

      <div class="panel-body">
        <h3 class="group-title">默认背景</h3>
        <div class="bg-grid">
          <button
            v-for="bgItem in DEFAULT_BACKGROUNDS"
            :key="bgItem.key"
            class="bg-card card"
            :class="{ active: selection === `default:${bgItem.key}` }"
            @click="choose(`default:${bgItem.key}`)"
          >
            <div class="thumb">
              <img
                v-if="!brokenDefaults[bgItem.key]"
                :src="bgItem.url"
                :alt="bgItem.label"
                @error="brokenDefaults[bgItem.key] = true"
              />
              <span v-else class="thumb-missing"><i class="fas fa-image"></i> 未提供</span>
            </div>
            <span class="bg-label">{{ bgItem.label }}</span>
            <span v-if="selection === `default:${bgItem.key}`" class="check">
              <i class="fas fa-check"></i>
            </span>
          </button>
        </div>

        <h3 class="group-title">
          我的上传
          <span class="count">{{ uploads.length }} / {{ MAX_UPLOADS }}</span>
        </h3>
        <div class="bg-grid">
          <button
            v-for="item in uploads"
            :key="item.id"
            class="bg-card card"
            :class="{ active: selection === `custom:${item.id}` }"
            @click="choose(`custom:${item.id}`)"
          >
            <div class="thumb">
              <img v-if="thumbUrls[item.id]" :src="thumbUrls[item.id]" alt="自定义背景" />
              <span v-else class="thumb-missing"><i class="fas fa-spinner fa-spin"></i></span>
            </div>
            <span class="bg-label">{{ item.originalName || `自定义 ${item.id}` }}</span>
            <span v-if="selection === `custom:${item.id}`" class="check">
              <i class="fas fa-check"></i>
            </span>
            <span class="del" title="删除这张背景" @click.stop="removeUpload(item.id)">
              <i class="fas fa-trash"></i>
            </span>
          </button>

          <button
            class="bg-card card upload-card"
            :disabled="uploading || uploads.length >= MAX_UPLOADS"
            @click="pickFile"
          >
            <div class="thumb upload-thumb">
              <i class="fas" :class="uploading ? 'fa-spinner fa-spin' : 'fa-plus'"></i>
            </div>
            <span class="bg-label">{{ uploading ? '处理中…' : '上传图片' }}</span>
          </button>
        </div>

        <p class="hint note">
          支持 JPEG / PNG / WebP，单张不超过 10MB，最多 10 张。上传后会自动压缩（长边 2560 / WebP）
          并设为当前背景。
        </p>
        <input
          ref="fileInput"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          class="hidden-input"
          @change="onFileChange"
        />

        <div class="divider"></div>

        <h3 class="group-title">显示效果</h3>
        <div class="display-grid">
          <div class="field">
            <span class="field-label">遮罩与模糊</span>
            <div class="seg">
              <button
                class="seg-btn"
                :class="{ active: mode === 'auto' }"
                @click="setMode('auto')"
              >
                自动（按图片明暗）
              </button>
              <button
                class="seg-btn"
                :class="{ active: mode === 'manual' }"
                @click="setMode('manual')"
              >
                手动
              </button>
            </div>
          </div>

          <template v-if="mode === 'manual'">
            <div class="field">
              <span class="field-label">遮罩强度：{{ manualDim }}%</span>
              <input
                class="range"
                type="range"
                min="0"
                max="100"
                step="5"
                v-model.number="manualDim"
                @change="saveDisplay"
              />
            </div>
            <div class="field">
              <span class="field-label">背景模糊：{{ manualBlur }}px</span>
              <input
                class="range"
                type="range"
                min="0"
                max="20"
                step="1"
                v-model.number="manualBlur"
                @change="saveDisplay"
              />
            </div>
          </template>

          <div class="field">
            <span class="field-label">适配方式</span>
            <select class="input" :value="fit" @change="onFitChange">
              <option value="cover">铺满（cover）</option>
              <option value="contain">完整显示（contain）</option>
            </select>
          </div>
        </div>
        <p class="hint note">
          自动模式会采样当前背景的亮度：亮图自动加深遮罩并轻微模糊，暗图保持通透，保证前台文字始终清晰。
        </p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { DEFAULT_BACKGROUNDS } from '@/assets/backgrounds'
import { fetchBackgroundImage } from '@/api/settings'
import { useBackgroundStore } from '@/stores/background'
import { prepareImage } from '@/utils/image'

const MAX_UPLOADS = 10
const MAX_BYTES = 10 * 1024 * 1024

const bgStore = useBackgroundStore()
const { selection, uploads, mode, fit } = storeToRefs(bgStore)

const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const message = ref('')
const messageType = ref<'ok' | 'err'>('ok')
const thumbUrls = ref<Record<number, string>>({})
const brokenDefaults = ref<Record<string, boolean>>({})

const manualDim = ref<number>(45)
const manualBlur = ref<number>(0)

const currentLabel = computed(() => {
  if (selection.value.startsWith('default:')) {
    const key = selection.value.slice('default:'.length)
    return DEFAULT_BACKGROUNDS.find((b) => b.key === key)?.label ?? key
  }
  const id = Number(selection.value.slice('custom:'.length))
  const item = uploads.value.find((u) => u.id === id)
  return item?.originalName || `自定义 ${id}`
})

watch(
  [() => bgStore.dim, () => bgStore.blur],
  () => {
    manualDim.value = bgStore.dim ?? 45
    manualBlur.value = bgStore.blur ?? 0
  },
  { immediate: true },
)

function flash(text: string, type: 'ok' | 'err' = 'ok') {
  message.value = text
  messageType.value = type
}

function errorText(e: unknown): string {
  const err = e as { response?: { data?: { detail?: string } }; message?: string }
  return err?.response?.data?.detail || err?.message || '操作失败'
}

function pickFile() {
  fileInput.value?.click()
}

async function choose(target: string) {
  if (target === selection.value) return
  try {
    await bgStore.select(target)
    flash('已切换背景')
  } catch (e) {
    flash(errorText(e), 'err')
  }
}

async function setMode(next: 'auto' | 'manual') {
  if (next === mode.value) return
  try {
    await bgStore.setDisplay({ mode: next, dim: manualDim.value, blur: manualBlur.value })
    flash(next === 'auto' ? '已切换为自动' : '已切换为手动')
  } catch (e) {
    flash(errorText(e), 'err')
  }
}

async function saveDisplay() {
  try {
    await bgStore.setDisplay({ dim: manualDim.value, blur: manualBlur.value })
  } catch (e) {
    flash(errorText(e), 'err')
  }
}

async function onFitChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value as 'cover' | 'contain'
  try {
    await bgStore.setDisplay({ fit: value })
  } catch (e) {
    flash(errorText(e), 'err')
  }
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    flash('请选择图片文件', 'err')
    return
  }
  if (file.size > MAX_BYTES) {
    flash('图片不能超过 10MB', 'err')
    return
  }

  uploading.value = true
  flash('正在处理并上传…')
  try {
    const prepared = await prepareImage(file)
    await bgStore.upload(prepared.blob, prepared.filename)
    await refreshThumbs()
    flash('背景已上传并设为当前背景')
  } catch (e) {
    flash(errorText(e), 'err')
  } finally {
    uploading.value = false
  }
}

async function removeUpload(id: number) {
  if (!window.confirm('确定删除这张背景图？')) return
  try {
    await bgStore.remove(id)
    await refreshThumbs()
    flash('已删除')
  } catch (e) {
    flash(errorText(e), 'err')
  }
}

async function refreshThumbs() {
  const next: Record<number, string> = {}
  for (const item of uploads.value) {
    const existing = thumbUrls.value[item.id]
    if (existing) {
      next[item.id] = existing
      continue
    }
    try {
      const blob = await fetchBackgroundImage(item.id)
      next[item.id] = URL.createObjectURL(blob)
    } catch {
      /* 忽略单张失败 */
    }
  }
  for (const [key, url] of Object.entries(thumbUrls.value)) {
    if (!next[Number(key)]) URL.revokeObjectURL(url)
  }
  thumbUrls.value = next
}

watch(
  () => uploads.value.map((u) => u.id).join(','),
  () => {
    void refreshThumbs()
  },
)

onMounted(async () => {
  if (!uploads.value.length) {
    await bgStore.load()
  }
  await refreshThumbs()
})

onUnmounted(() => {
  Object.values(thumbUrls.value).forEach((url) => URL.revokeObjectURL(url))
})
</script>

<style scoped>
.group-title {
  margin: 0 0 var(--sp-3);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
}
.group-title .count {
  margin-left: 0.4rem;
  font-size: 0.72rem;
  color: var(--text-faint);
  font-weight: 400;
}
.group-title:not(:first-child) {
  margin-top: var(--sp-5);
}

.divider {
  height: 1px;
  margin: var(--sp-5) 0;
  background: var(--border);
}

.bg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--sp-3);
}

.bg-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.5rem;
  cursor: pointer;
  transition:
    border-color 0.15s,
    transform 0.15s,
    background 0.15s;
}
.bg-card:hover:not(:disabled) {
  transform: translateY(-2px);
  border-color: var(--accent-border);
}
.bg-card.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.bg-card:disabled {
  opacity: 0.45;
  cursor: default;
}

.thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: var(--r-sm);
  overflow: hidden;
  background: rgba(2, 6, 23, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.thumb-missing {
  font-size: 0.72rem;
  color: var(--text-faint);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
}
.thumb-missing i {
  font-size: 1rem;
}
.upload-thumb {
  border: 1px dashed var(--border-strong);
  color: var(--text-faint);
  font-size: 1.3rem;
}

.bg-label {
  font-size: 0.78rem;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

.check {
  position: absolute;
  top: 0.7rem;
  right: 0.7rem;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 0.62rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
.del {
  position: absolute;
  top: 0.7rem;
  left: 0.7rem;
  width: 22px;
  height: 22px;
  border-radius: var(--r-sm);
  background: rgba(2, 6, 23, 0.75);
  color: #fca5b3;
  font-size: 0.7rem;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}
.bg-card:hover .del {
  opacity: 1;
}
.del:hover {
  background: rgba(232, 93, 117, 0.3);
}

.note {
  margin-top: var(--sp-4);
}

/* 显示效果 */
.display-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--sp-4);
  align-items: end;
}
.seg {
  display: inline-flex;
  padding: 3px;
  gap: 3px;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: rgba(2, 6, 23, 0.4);
}
.seg-btn {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.78rem;
  padding: 0.4rem 0.7rem;
  border-radius: 6px;
  cursor: pointer;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.seg-btn:hover {
  color: var(--text);
}
.seg-btn.active {
  background: var(--accent-soft);
  color: #bfdbfe;
}
.range {
  width: 100%;
  accent-color: var(--accent);
}
select.input {
  cursor: pointer;
}

.hidden-input {
  display: none;
}
</style>
