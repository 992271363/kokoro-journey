// frontend/src/api/settings.ts
// 用户偏好：背景图库（内置默认 + 账号上传）
import axios from 'axios'
import request from '@/utils/request'
import { useAuthStore } from '@/stores/auth'

export interface UserBackground {
  id: number
  url: string
  originalName?: string | null
  size: number
  createdAt?: string | null
}

export interface BackgroundState {
  background: string
  mode: string
  dim?: number | null
  blur?: number | null
  fit: string
  uploads: UserBackground[]
}

export interface BackgroundDisplay {
  mode: 'auto' | 'manual'
  dim?: number | null
  blur?: number | null
  fit: 'cover' | 'contain'
}

export function getBackground() {
  return request.get('/settings/background') as unknown as Promise<BackgroundState>
}

export function setBackground(background: string) {
  return request.put('/settings/background', { background }) as unknown as Promise<BackgroundState>
}

export function setBackgroundDisplay(display: BackgroundDisplay) {
  return request.put(
    '/settings/background/display',
    display,
  ) as unknown as Promise<BackgroundState>
}

export function uploadBackground(file: Blob, filename: string) {
  const form = new FormData()
  form.append('file', file, filename)
  return request.post('/settings/background/upload', form, {
    timeout: 120000,
  }) as unknown as Promise<UserBackground>
}

export function deleteBackground(imageId: number) {
  return request.delete(
    `/settings/background/images/${imageId}`,
  ) as unknown as Promise<BackgroundState>
}

// 图片接口同样需要 Authorization，而 CSS/<img> 带不上请求头，故统一取 blob。
const imageClient = axios.create({ baseURL: '/api', timeout: 60000 })

imageClient.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

export async function fetchBackgroundImage(imageId: number): Promise<Blob> {
  const res = await imageClient.get(`/settings/background/images/${imageId}`, {
    responseType: 'blob',
  })
  return res.data as Blob
}
