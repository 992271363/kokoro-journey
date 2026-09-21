// frontend/src/stores/background.ts
import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  deleteBackground as apiDelete,
  fetchBackgroundImage,
  getBackground,
  setBackground as apiSet,
  setBackgroundDisplay as apiSetDisplay,
  uploadBackground as apiUpload,
  type BackgroundDisplay,
  type UserBackground,
} from '@/api/settings'
import { defaultBackgroundUrl, FALLBACK_BACKGROUND } from '@/assets/backgrounds'
import { averageLuminance, imageLoads, luminanceToEffect, type BackgroundEffect } from '@/utils/image'

const STORAGE_KEY = 'app_background'

type FitMode = 'cover' | 'contain'

export const useBackgroundStore = defineStore('background', () => {
  const selection = ref<string>(localStorage.getItem(STORAGE_KEY) || FALLBACK_BACKGROUND)
  const uploads = ref<UserBackground[]>([])
  const mode = ref<'auto' | 'manual'>('auto')
  const dim = ref<number | null>(null)
  const blur = ref<number | null>(null)
  const fit = ref<FitMode>('cover')

  const loading = ref(false)
  const error = ref('')

  let objectUrl: string | null = null
  const luminanceCache = new Map<string, number | null>()

  function applyVars(url: string | undefined, effect: BackgroundEffect, fitMode: FitMode) {
    const root = document.documentElement.style
    if (url) {
      root.setProperty('--app-bg', `url("${url}")`)
    } else {
      root.setProperty('--app-bg', 'none')
    }
    root.setProperty('--app-dim', `rgba(2, 6, 23, ${(effect.dim / 100).toFixed(3)})`)
    root.setProperty('--app-blur', `${effect.blur}px`)
    root.setProperty('--app-scale', String(effect.scale))
    root.setProperty('--app-fit', fitMode)
  }

  function releaseObjectUrl() {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl)
      objectUrl = null
    }
  }

  async function resolveUrl(sel: string): Promise<string | undefined> {
    if (sel.startsWith('default:')) {
      releaseObjectUrl()
      const url = defaultBackgroundUrl(sel.slice('default:'.length))
      if (url && (await imageLoads(url))) return url
      // 该默认图缺失 → 回落 BG1
      return defaultBackgroundUrl('BG1')
    }
    if (sel.startsWith('custom:')) {
      releaseObjectUrl()
      const id = Number(sel.slice('custom:'.length))
      if (!id) return defaultBackgroundUrl('BG1')
      try {
        const blob = await fetchBackgroundImage(id)
        const url = URL.createObjectURL(blob)
        objectUrl = url
        return url
      } catch {
        return defaultBackgroundUrl('BG1')
      }
    }
    return defaultBackgroundUrl('BG1')
  }

  async function apply(sel: string) {
    const url = await resolveUrl(sel)
    let effect: BackgroundEffect
    if (mode.value === 'auto') {
      let luminance = luminanceCache.get(sel)
      if (luminance === undefined) {
        luminance = url ? await averageLuminance(url) : null
        luminanceCache.set(sel, luminance)
      }
      effect = luminanceToEffect(luminance ?? 0.2)
    } else {
      const b = blur.value ?? 0
      effect = { dim: dim.value ?? 45, blur: b, scale: b > 0 ? 1 + b * 0.006 : 1 }
    }
    applyVars(url, effect, fit.value)
  }

  function syncState(state: {
    background: string
    mode: string
    dim?: number | null
    blur?: number | null
    fit: string
    uploads: UserBackground[]
  }) {
    selection.value = state.background || FALLBACK_BACKGROUND
    mode.value = state.mode === 'manual' ? 'manual' : 'auto'
    dim.value = state.dim ?? null
    blur.value = state.blur ?? null
    fit.value = state.fit === 'contain' ? 'contain' : 'cover'
    uploads.value = state.uploads || []
    localStorage.setItem(STORAGE_KEY, selection.value)
  }

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const state = await getBackground()
      syncState(state)
      await apply(selection.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : '背景设置加载失败'
      await apply(selection.value)
    } finally {
      loading.value = false
    }
  }

  async function select(sel: string) {
    const prev = selection.value
    selection.value = sel
    await apply(sel)
    try {
      const state = await apiSet(sel)
      syncState(state)
      await apply(selection.value)
    } catch (e) {
      selection.value = prev
      await apply(prev)
      throw e
    }
  }

  async function setDisplay(patch: Partial<BackgroundDisplay>) {
    const payload: BackgroundDisplay = {
      mode: (patch.mode ?? mode.value) as 'auto' | 'manual',
      dim: patch.dim !== undefined ? patch.dim : dim.value,
      blur: patch.blur !== undefined ? patch.blur : blur.value,
      fit: (patch.fit ?? fit.value) as FitMode,
    }
    const state = await apiSetDisplay(payload)
    syncState(state)
    await apply(selection.value)
  }

  async function upload(blob: Blob, filename: string) {
    const created = await apiUpload(blob, filename)
    await load() // 上传后服务端会自动设为当前背景
    return created
  }

  async function remove(imageId: number) {
    const state = await apiDelete(imageId)
    syncState(state)
    luminanceCache.delete(selection.value)
    await apply(selection.value)
  }

  function reset() {
    releaseObjectUrl()
    selection.value = FALLBACK_BACKGROUND
    uploads.value = []
    mode.value = 'auto'
    dim.value = null
    blur.value = null
    fit.value = 'cover'
    error.value = ''
    localStorage.removeItem(STORAGE_KEY)
    applyVars(defaultBackgroundUrl('BG1'), luminanceToEffect(0.2), 'cover')
  }

  return {
    selection,
    uploads,
    mode,
    dim,
    blur,
    fit,
    loading,
    error,
    load,
    select,
    setDisplay,
    upload,
    remove,
    reset,
  }
})
