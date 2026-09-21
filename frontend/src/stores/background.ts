// frontend/src/stores/background.ts
import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  deleteBackground as apiDelete,
  fetchBackgroundImage,
  getBackground,
  setBackground as apiSet,
  uploadBackground as apiUpload,
  type UserBackground,
} from '@/api/settings'
import { defaultBackgroundUrl, FALLBACK_BACKGROUND } from '@/assets/backgrounds'

const STORAGE_KEY = 'app_background'

export const useBackgroundStore = defineStore('background', () => {
  const selection = ref<string>(localStorage.getItem(STORAGE_KEY) || FALLBACK_BACKGROUND)
  const uploads = ref<UserBackground[]>([])
  const loading = ref(false)
  const error = ref('')

  let objectUrl: string | null = null

  function applyUrl(url: string | undefined) {
    const root = document.documentElement
    if (url) {
      root.style.setProperty('--app-bg', `url("${url}")`)
    } else {
      root.style.removeProperty('--app-bg')
    }
  }

  function releaseObjectUrl() {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl)
      objectUrl = null
    }
  }

  async function applySelection(sel: string) {
    if (sel.startsWith('default:')) {
      releaseObjectUrl()
      applyUrl(defaultBackgroundUrl(sel.slice('default:'.length)))
      return
    }
    if (sel.startsWith('custom:')) {
      const id = Number(sel.slice('custom:'.length))
      releaseObjectUrl()
      if (!id) {
        applyUrl(defaultBackgroundUrl('BG1'))
        return
      }
      try {
        const blob = await fetchBackgroundImage(id)
        objectUrl = URL.createObjectURL(blob)
        applyUrl(objectUrl)
      } catch {
        applyUrl(defaultBackgroundUrl('BG1'))
      }
      return
    }
    applyUrl(defaultBackgroundUrl('BG1'))
  }

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const state = await getBackground()
      selection.value = state.background || FALLBACK_BACKGROUND
      uploads.value = state.uploads || []
      localStorage.setItem(STORAGE_KEY, selection.value)
      await applySelection(selection.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : '背景设置加载失败'
      await applySelection(selection.value)
    } finally {
      loading.value = false
    }
  }

  async function select(sel: string) {
    const prev = selection.value
    selection.value = sel
    await applySelection(sel)
    try {
      const state = await apiSet(sel)
      selection.value = state.background
      uploads.value = state.uploads || []
      localStorage.setItem(STORAGE_KEY, selection.value)
    } catch (e) {
      selection.value = prev
      await applySelection(prev)
      throw e
    }
  }

  async function upload(blob: Blob, filename: string) {
    const created = await apiUpload(blob, filename)
    await load() // 上传后服务端会自动设为当前背景，重新同步状态
    return created
  }

  async function remove(imageId: number) {
    const state = await apiDelete(imageId)
    selection.value = state.background
    uploads.value = state.uploads || []
    localStorage.setItem(STORAGE_KEY, selection.value)
    await applySelection(selection.value)
  }

  function reset() {
    releaseObjectUrl()
    selection.value = FALLBACK_BACKGROUND
    uploads.value = []
    error.value = ''
    localStorage.removeItem(STORAGE_KEY)
    applyUrl(defaultBackgroundUrl('BG1'))
  }

  return { selection, uploads, loading, error, load, select, upload, remove, reset }
})
