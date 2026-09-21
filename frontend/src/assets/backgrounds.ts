// 五张内置默认背景（放在 public/backgrounds/ 下，按固定 URL 引用）。
// BG2–BG5 可后续填充；缺失时只是 404，不影响构建与页面（回落到 body 的兜底色）。
export interface DefaultBackground {
  key: string
  label: string
  url: string
}

export const DEFAULT_BACKGROUND_KEYS = ['BG1', 'BG2', 'BG3', 'BG4', 'BG5']

export const DEFAULT_BACKGROUNDS: DefaultBackground[] = DEFAULT_BACKGROUND_KEYS.map(
  (key, index) => ({
    key,
    label: `默认 ${index + 1}`,
    url: `/backgrounds/${key}.jpg`,
  }),
)

export function defaultBackgroundUrl(key: string): string | undefined {
  return DEFAULT_BACKGROUNDS.find((b) => b.key === key)?.url
}

export const FALLBACK_BACKGROUND = 'default:BG1'
