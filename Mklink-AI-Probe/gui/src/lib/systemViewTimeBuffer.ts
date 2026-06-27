export interface TimeRange {
  start: number
  end: number
}

export function filterRangesByWindow<T extends TimeRange>(
  ranges: readonly T[],
  latestTime: number,
  windowSize: number,
): T[] {
  if (!Number.isFinite(latestTime) || !Number.isFinite(windowSize) || windowSize <= 0) {
    return [...ranges]
  }
  const cutoff = latestTime - windowSize
  return ranges.filter(range => range.end >= cutoff)
}

export function appendAndTrimRanges<T extends TimeRange>(
  ranges: readonly T[],
  additions: readonly T[],
  latestTime: number,
  bufferSize: number,
  maxItems: number,
): T[] {
  const limit = Math.max(0, Math.floor(maxItems))
  if (limit === 0) return []
  const cutoff = Number.isFinite(latestTime) && Number.isFinite(bufferSize) && bufferSize > 0
    ? latestTime - bufferSize
    : -Infinity
  const next = [...ranges, ...additions].filter(range => range.end >= cutoff)
  return next.length > limit ? next.slice(-limit) : next
}

export function appendAndTrimEventsByTime<T>(
  events: readonly T[],
  additions: readonly T[],
  latestTime: number,
  bufferSize: number,
  maxItems: number,
  getTime: (event: T) => number,
): T[] {
  const limit = Math.max(0, Math.floor(maxItems))
  if (limit === 0) return []
  const cutoff = Number.isFinite(latestTime) && Number.isFinite(bufferSize) && bufferSize > 0
    ? latestTime - bufferSize
    : -Infinity
  const next = [...events, ...additions].filter(event => {
    const time = getTime(event)
    return !Number.isFinite(time) || time >= cutoff
  })
  return next.length > limit ? next.slice(-limit) : next
}
