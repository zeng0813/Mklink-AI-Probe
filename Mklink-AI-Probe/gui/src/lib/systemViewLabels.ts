export function formatScheduleCount(count: number): string {
  const value = Number.isFinite(count) ? Math.max(0, Math.floor(count)) : 0
  return `${value.toLocaleString()}\u6b21\u8c03\u5ea6`
}
