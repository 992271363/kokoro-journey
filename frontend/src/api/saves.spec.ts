import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('axios', () => {
  const client = {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() } },
  }
  return { default: { create: vi.fn(() => client) } }
})

import axios from 'axios'
import request from '@/utils/request'
import {
  downloadFile,
  downloadSlotZip,
  filenameFromDisposition,
  listFiles,
  listGames,
  listSlots,
} from '@/api/saves'

const client = (axios.create as unknown as ReturnType<typeof vi.fn>).mock.results[0]!.value as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('cloud saves api (read-only)', () => {
  it('listGames / listSlots / listFiles 拼接正确路径', async () => {
    ;(request.get as ReturnType<typeof vi.fn>).mockResolvedValue([])
    await listGames()
    await listSlots(3)
    await listFiles(3, 9)
    expect(request.get).toHaveBeenNthCalledWith(1, '/saves/games')
    expect(request.get).toHaveBeenNthCalledWith(2, '/saves/games/3/slots')
    expect(request.get).toHaveBeenNthCalledWith(3, '/saves/games/3/versions/9/files')
  })

  it('downloadFile 使用 blob 且从 Content-Disposition 取文件名', async () => {
    client.get.mockResolvedValue({
      data: new Blob(['x']),
      headers: {
        'content-disposition': "attachment; filename*=UTF-8''%E5%AD%98%E6%A1%A3.sav",
      },
    })
    const res = await downloadFile(3, 9, 'save/a.sav')
    expect(client.get).toHaveBeenCalledWith(
      '/saves/games/3/versions/9/files/download',
      { params: { path: 'save/a.sav' }, responseType: 'blob' },
    )
    expect(res.filename).toBe('存档.sav')
  })

  it('downloadSlotZip 请求整槽 zip', async () => {
    client.post.mockResolvedValue({ data: new Blob(['z']), headers: {} })
    const res = await downloadSlotZip(3, 9, 'my-save-存档位2.zip')
    expect(client.post).toHaveBeenCalledWith(
      '/saves/games/3/versions/9/files-batch-download',
      { paths: [] },
      { responseType: 'blob' },
    )
    expect(res.filename).toBe('my-save-存档位2.zip')
  })

  it('filenameFromDisposition 兼容普通与 RFC5987 形式', () => {
    expect(filenameFromDisposition('attachment; filename="a.sav"', 'f')).toBe('a.sav')
    expect(filenameFromDisposition("attachment; filename*=UTF-8''%E4%B8%AD.sav", 'f')).toBe(
      '中.sav',
    )
    expect(filenameFromDisposition(undefined, 'fallback.sav')).toBe('fallback.sav')
  })
})
