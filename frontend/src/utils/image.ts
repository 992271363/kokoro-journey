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
