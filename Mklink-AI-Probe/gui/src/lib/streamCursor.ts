export interface StreamSequenced {
  _streamSeq?: number
}

export function takeNewStreamPoints<T extends StreamSequenced>(
  points: readonly T[],
  lastSeq: number,
): { points: T[]; nextSeq: number } {
  const nextPoints: T[] = []
  let nextSeq = lastSeq

  for (const point of points) {
    const seq = point._streamSeq
    if (typeof seq !== 'number' || seq <= lastSeq) continue
    nextPoints.push(point)
    if (seq > nextSeq) nextSeq = seq
  }

  return { points: nextPoints, nextSeq }
}
