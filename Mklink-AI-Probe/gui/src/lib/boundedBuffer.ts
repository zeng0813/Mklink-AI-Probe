export function trimToLast<T>(items: T[], maxItems: number): void {
  const limit = Math.max(0, Math.floor(maxItems))
  const removeCount = items.length - limit
  if (removeCount > 0) items.splice(0, removeCount)
}

export function appendManyToLast<T>(
  items: readonly T[],
  additions: readonly T[],
  maxItems: number,
): T[] {
  const limit = Math.max(0, Math.floor(maxItems))
  if (limit === 0) return []
  const next = [...items, ...additions]
  return next.length > limit ? next.slice(-limit) : next
}
