<template>
  <div class="settings-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Settings</p>
        <h1>设置</h1>
      </div>
    </header>

    <p v-if="message" class="flash" :class="messageType">
      <i class="fas" :class="messageType === 'ok' ? 'fa-circle-check' : 'fa-triangle-exclamation'"></i>
      {{ message }}
    </p>

    <section class="panel">
      <div class="panel-header">
        <h2>背景</h2>
        <span class="panel-badge">当前：{{ currentLabel }}</span>
      </div>

      <div class="panel-body">
        <h3 class="group-title">默认背景</h3>
        <div class="bg-grid">
          <button
            v-for="bgItem in DEFAULT_BACKGROUNDS"
            :key="bgItem.key"
            class="bg-card"
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
            class="bg-card"
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
            class="bg-card upload-card"
            :disabled="uploading || uploads.length >= MAX_UPLOADS"
            @click="pickFile"
          >
            <div class="thumb upload-thumb">
              <i class="fas" :class="uploading ? 'fa-spinner fa-spin' : 'fa-plus'"></i>
            </div>
            <span class="bg-label">{{ uploading ? '处理中…' : '上传图片' }}</span>
          </button>
        </div>

        <p class="hint">
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
const { selection, uploads } = storeToRefs(bgStore)

const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const message = ref('')
const messageType = ref<'ok' | 'err'>('ok')
const thumbUrls = ref<Record<number, string>>({})
const brokenDefaults = ref<Record<string, boolean>>({})

const currentLabel = computed(() => {
  if (selection.value.startsWith('default:')) {
    const key = selection.value.slice('default:'.length)
    return DEFAULT_BACKGROUNDS.find((b) => b.key === key)?.label ?? key
  }
  const id = Number(selection.value.slice('custom:'.length))
  const item = uploads.value.find((u) => u.id === id)
  return item?.originalName || `自定义 ${id}`
})

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
.settings-page {
  font-family: 'DM Sans', sans-serif;
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 2.5rem 3rem;
  color: #e2e8f0;
}

.page-header {
  margin-bottom: 1.5rem;
}
.page-header h1 {
  margin: 0;
  font-size: 2rem;
  font-weight: 600;
  color: #f1f5f9;
  letter-spacing: -0.02em;
}
.eyebrow {
  margin: 0 0 0.25rem;
  font-size: 0.9rem;
  color: #64748b;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.flash {
  margin: 0 0 1rem;
  padding: 0.65rem 1rem;
  border-radius: 8px;
  font-size: 0.85rem;
}
.flash.ok {
  background: rgba(52, 200, 138, 0.12);
  border: 1px solid rgba(52, 200, 138, 0.35);
  color: #86efac;
}
.flash.err {
  background: rgba(232, 93, 117, 0.12);
  border: 1px solid rgba(232, 93, 117, 0.35);
  color: #fca5b3;
}

.panel {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 16px;
  overflow: hidden;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 1.4rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.panel-header h2 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: #cbd5e1;
}
.panel-badge {
  font-size: 0.72rem;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  padding: 0.2rem 0.7rem;
}
.panel-body {
  padding: 1.25rem 1.4rem 1.5rem;
}

.group-title {
  margin: 0 0 0.85rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: #cbd5e1;
}
.group-title .count {
  margin-left: 0.4rem;
  font-size: 0.72rem;
  color: #64748b;
  font-weight: 400;
}
.group-title:not(:first-child) {
  margin-top: 1.5rem;
}

.bg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 0.85rem;
}

.bg-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.5rem;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(30, 41, 59, 0.5);
  color: #cbd5e1;
  cursor: pointer;
  transition:
    border-color 0.15s,
    transform 0.15s,
    background 0.15s;
}
.bg-card:hover:not(:disabled) {
  transform: translateY(-2px);
  border-color: rgba(79, 156, 249, 0.5);
}
.bg-card.active {
  border-color: #4f9cf9;
  background: rgba(79, 156, 249, 0.12);
}
.bg-card:disabled {
  opacity: 0.45;
  cursor: default;
}

.thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  overflow: hidden;
  background: #0f172a;
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
  color: #475569;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
}
.thumb-missing i {
  font-size: 1rem;
}

.upload-thumb {
  border: 1px dashed rgba(255, 255, 255, 0.18);
  color: #64748b;
  font-size: 1.3rem;
}

.bg-label {
  font-size: 0.78rem;
  color: #cbd5e1;
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
  background: #4f9cf9;
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
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.75);
  color: #fca5a3;
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

.hint {
  margin: 1.25rem 0 0;
  font-size: 0.75rem;
  color: #64748b;
  line-height: 1.6;
}

.hidden-input {
  display: none;
}

@media (max-width: 640px) {
  .settings-page {
    padding: 1rem;
  }
}
</style>
