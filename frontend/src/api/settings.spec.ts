import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('axios', () => {
  const client = {
    get: vi.fn(),
    interceptors: { request: { use: vi.fn() } },
  }
  return { default: { create: vi.fn(() => client) } }
})

import axios from 'axios'
import request from '@/utils/request'
import {
  deleteBackground,
  fetchBackgroundImage,
  getBackground,
  setBackground,
  setBackgroundDisplay,
  uploadBackground,
} from '@/api/settings'
import { DEFAULT_BACKGROUNDS, defaultBackgroundUrl, FALLBACK_BACKGROUND } from '@/assets/backgrounds'

const client = (axios.create as unknown as ReturnType<typeof vi.fn>).mock.results[0]!.value as {
  get: ReturnType<typeof vi.fn>
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('background settings api', () => {
  it('读取/设置/删除 命中正确路径', async () => {
    ;(request.get as ReturnType<typeof vi.fn>).mockResolvedValue({ background: 'default:BG1', uploads: [] })
    ;(request.put as ReturnType<typeof vi.fn>).mockResolvedValue({ background: 'default:BG2', uploads: [] })
    ;(request.delete as ReturnType<typeof vi.fn>).mockResolvedValue({ background: 'default:BG1', uploads: [] })

    await getBackground()
    await setBackground('default:BG2')
    await deleteBackground(5)

    expect(request.get).toHaveBeenCalledWith('/settings/background')
    expect(request.put).toHaveBeenCalledWith('/settings/background', { background: 'default:BG2' })
    expect(request.delete).toHaveBeenCalledWith('/settings/background/images/5')
  })

  it('设置显示参数', async () => {
    ;(request.put as ReturnType<typeof vi.fn>).mockResolvedValue({
      background: 'default:BG1',
      mode: 'manual',
      dim: 70,
      blur: 10,
      fit: 'contain',
      uploads: [],
    })
    const state = await setBackgroundDisplay({
      mode: 'manual',
      dim: 70,
      blur: 10,
      fit: 'contain',
    })
    expect(request.put).toHaveBeenCalledWith('/settings/background/display', {
      mode: 'manual',
      dim: 70,
      blur: 10,
      fit: 'contain',
    })
    expect(state.mode).toBe('manual')
  })

  it('上传以 multipart 发送文件', async () => {
    ;(request.post as ReturnType<typeof vi.fn>).mockResolvedValue({ id: 1 })
    const blob = new Blob(['x'], { type: 'image/webp' })
    await uploadBackground(blob, 'bg.webp')

    const [url, form, config] = (request.post as ReturnType<typeof vi.fn>).mock.calls[0]!
    expect(url).toBe('/settings/background/upload')
    expect(form).toBeInstanceOf(FormData)
    expect((form as FormData).get('file')).toBeTruthy()
    expect(config).toMatchObject({ timeout: 120000 })
  })

  it('取图使用 blob 响应', async () => {
    client.get.mockResolvedValue({ data: new Blob(['img']) })
    const blob = await fetchBackgroundImage(7)
    expect(client.get).toHaveBeenCalledWith('/settings/background/images/7', {
      responseType: 'blob',
    })
    expect(blob).toBeInstanceOf(Blob)
  })

  it('内置默认背景映射', () => {
    expect(DEFAULT_BACKGROUNDS).toHaveLength(5)
    expect(DEFAULT_BACKGROUNDS[0]).toEqual({
      key: 'BG1',
      label: '默认 1',
      url: '/backgrounds/BG1.jpg',
    })
    expect(defaultBackgroundUrl('BG5')).toBe('/backgrounds/BG5.jpg')
    expect(defaultBackgroundUrl('NOPE')).toBeUndefined()
    expect(FALLBACK_BACKGROUND).toBe('default:BG1')
  })
})
