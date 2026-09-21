// frontend/src/utils/image.ts
// 上传前在浏览器端预压缩：纠正方向、限制长边、转 WebP，尽量减小上传体积。
// 服务端还会用 Pillow 做权威规范化，这里只是省流量与提速。

const MAX_EDGE = 2560
const WEBP_QUALITY = 0.82
const JPEG_QUALITY = 0.85

export interface PreparedImage {
  blob: Blob
  filename: string
}

function fit(width: number, height: number, maxEdge: number): [number, number] {
  const longest = Math.max(width, height)
  if (longest <= maxEdge) return [width, height]
  const scale = maxEdge / longest
  return [Math.max(1, Math.round(width * scale)), Math.max(1, Math.round(height * scale))]
}

async function loadSource(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file, { imageOrientation: 'from-image' })
    } catch {
      /* 回落 <img> */
    }
  }
  return await new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      resolve(img)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('无法读取图片'))
    }
    img.src = url
  })
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    if (typeof canvas.toBlob !== 'function') {
      resolve(null)
      return
    }
    canvas.toBlob((blob) => resolve(blob), type, quality)
  })
}

function withExtension(name: string, ext: string): string {
  const base = name.replace(/\.[^.]+$/, '')
  return `${base || 'background'}${ext}`
}

export async function prepareImage(file: File): Promise<PreparedImage> {
  const fallback: PreparedImage = { blob: file, filename: file.name }
  if (!file.type.startsWith('image/')) return fallback

  try {
    const source = await loadSource(file)
    const [width, height] = fit(source.width, source.height, MAX_EDGE)

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) return fallback
    ctx.drawImage(source, 0, 0, width, height)
    if (source instanceof ImageBitmap) source.close()

    let blob = await canvasToBlob(canvas, 'image/webp', WEBP_QUALITY)
    if (!blob || blob.type !== 'image/webp') {
      blob = await canvasToBlob(canvas, 'image/jpeg', JPEG_QUALITY)
    }
    if (!blob || blob.size >= file.size) return fallback

    const ext = blob.type === 'image/webp' ? '.webp' : '.jpg'
    return { blob, filename: withExtension(file.name, ext) }
  } catch {
    return fallback
  }
}

// ── 背景明暗 → 遮罩/模糊（auto 模式） ──────────────────────────────

export interface BackgroundEffect {
  /** 遮罩强度百分比 0..100 */
  dim: number
  /** 模糊像素 0..20 */
  blur: number
  /** 模糊时为遮住边缘而放大的倍率 */
  scale: number
}

/**
 * 依据图片平均亮度（0 暗 ~ 1 亮）推算遮罩与模糊：
 * 暗图轻遮罩、亮图重遮罩并轻微模糊，保证前景文字始终可读。
 */
export function luminanceToEffect(luminance: number): BackgroundEffect {
  const l = Math.min(1, Math.max(0, Number.isFinite(luminance) ? luminance : 0.2))
  const dim = Math.round((0.2 + 0.45 * l) * 100)
  const blur = l > 0.75 ? 6 : l > 0.5 ? 3 : 0
  const scale = blur > 0 ? 1 + blur * 0.006 : 1
  return { dim, blur, scale }
}

async function loadImage(url: string): Promise<HTMLImageElement> {
  return await new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('图片加载失败'))
    img.src = url
  })
}

/** 探测图片是否可加载（用于默认背景缺图时回落）。 */
export async function imageLoads(url: string): Promise<boolean> {
  try {
    await loadImage(url)
    return true
  } catch {
    return false
  }
}

/** 采样图片的平均相对亮度；失败返回 null。 */
export async function averageLuminance(url: string): Promise<number | null> {
  try {
    const img = await loadImage(url)
    const canvas = document.createElement('canvas')
    canvas.width = 24
    canvas.height = 24
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height)
    let sum = 0
    let count = 0
    for (let i = 0; i + 2 < data.length; i += 4) {
      const r = data[i] ?? 0
      const g = data[i + 1] ?? 0
      const b = data[i + 2] ?? 0
      sum += (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
      count += 1
    }
    return count ? sum / count : null
  } catch {
    return null
  }
}
