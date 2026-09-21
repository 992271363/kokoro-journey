// frontend/src/api/saves.ts
// 云存档只读浏览接口（网页端：浏览 + 下载，不做任何写操作）
import axios from 'axios'
import request from '@/utils/request'
import { useAuthStore } from '@/stores/auth'

export interface SaveGame {
  id: number
  name: string
  identifier?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  latestVersion?: number | null
  latestVersionId?: number | null
  latestTotalSize?: number | null
  latestFileCount?: number | null
  latestCreatedAt?: string | null
}

export interface SaveSlot {
  slot: number
  versionId?: number | null
  createdAt?: string | null
  totalSize?: number | null
  fileCount?: number | null
  label?: string | null
}

export interface SaveFile {
  path: string
  size: number
  sha256: string
  mtimeNs?: number | null
}

export function listGames() {
  return request.get('/saves/games') as unknown as Promise<SaveGame[]>
}

export function listSlots(gameId: number) {
  return request.get(`/saves/games/${gameId}/slots`) as unknown as Promise<SaveSlot[]>
}

export function listFiles(gameId: number, versionId: number) {
  return request.get(
    `/saves/games/${gameId}/versions/${versionId}/files`,
  ) as unknown as Promise<SaveFile[]>
}

// 下载需要读取 Content-Disposition 文件名，因此用独立实例（responseType=blob）
const downloadClient = axios.create({ baseURL: '/api', timeout: 300000 })

downloadClient.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

function basename(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path
}

export function filenameFromDisposition(
  disposition: string | undefined,
  fallback: string,
): string {
  if (!disposition) return fallback
  // RFC 5987: filename*=UTF-8''%E4%B8%AD%E6%96%87.sav
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(disposition)
  if (star && star[1]) {
    try {
      return decodeURIComponent(star[1].replace(/^"|"$/g, '').trim())
    } catch {
      /* 忽略解码失败 */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition)
  if (plain && plain[1]) return plain[1].trim()
  return fallback
}

export async function downloadFile(gameId: number, versionId: number, path: string) {
  const res = await downloadClient.get(
    `/saves/games/${gameId}/versions/${versionId}/files/download`,
    { params: { path }, responseType: 'blob' },
  )
  return {
    blob: res.data as Blob,
    filename: filenameFromDisposition(
      res.headers['content-disposition'] as string | undefined,
      basename(path),
    ),
  }
}

export async function downloadSlotZip(
  gameId: number,
  versionId: number,
  filename: string,
) {
  const res = await downloadClient.post(
    `/saves/games/${gameId}/versions/${versionId}/files-batch-download`,
    { paths: [] },
    { responseType: 'blob' },
  )
  return { blob: res.data as Blob, filename }
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'download'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
