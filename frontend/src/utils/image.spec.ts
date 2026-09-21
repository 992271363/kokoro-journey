import { describe, it, expect } from 'vitest'
import { luminanceToEffect } from '@/utils/image'

describe('luminanceToEffect（按图片亮度推导遮罩/模糊）', () => {
  it('暗图：轻遮罩、无模糊', () => {
    const effect = luminanceToEffect(0.1)
    expect(effect.dim).toBe(25)
    expect(effect.blur).toBe(0)
    expect(effect.scale).toBe(1)
  })

  it('中等亮度：轻微模糊', () => {
    expect(luminanceToEffect(0.6).blur).toBe(3)
    expect(luminanceToEffect(0.4).blur).toBe(0)
  })

  it('亮图：重遮罩 + 模糊 + 放大', () => {
    const effect = luminanceToEffect(0.9)
    expect(effect.dim).toBe(61)
    expect(effect.blur).toBe(6)
    expect(effect.scale).toBeGreaterThan(1)
  })

  it('越界/非法输入被夹取', () => {
    expect(luminanceToEffect(-1).dim).toBe(20)
    expect(luminanceToEffect(2).dim).toBe(65)
    expect(luminanceToEffect(Number.NaN).dim).toBe(29)
  })
})
