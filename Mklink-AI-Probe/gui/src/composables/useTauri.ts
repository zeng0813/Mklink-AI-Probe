// 极简的 Tauri 桥接：在 Tauri 环境（window.__TAURI__）调原生能力；
// 浏览器环境降级为 toast 警告。
import { useToast } from './useToast'

export function useTauri() {
  const toast = useToast()

  async function openInExplorer(path: string | null): Promise<void> {
    if (!path) {
      toast.warn('无固件目录路径')
      return
    }
    const tauri: any = (window as any).__TAURI__
    if (!tauri?.opener?.openPath) {
      toast.warn('仅 Tauri 桌面应用支持打开目录')
      return
    }
    try {
      await tauri.opener.openPath(path)
    } catch (e: any) {
      toast.warn(`打开目录失败：${e?.message ?? e}`)
    }
  }

  return { openInExplorer }
}
