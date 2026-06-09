/** Float64Array-based ring buffer for chart data. O(1) push/shift, zero GC pressure. */
export class RingBuffer {
  buffer: Float64Array
  capacity: number
  head = 0
  tail = 0
  count = 0
  _min = Infinity
  _max = -Infinity

  constructor(capacity: number) {
    this.capacity = capacity
    this.buffer = new Float64Array(capacity * 2) // [timestamp, value] pairs
  }

  push(t: number, v: number): void {
    const idx = this.head * 2
    if (this.count >= this.capacity) {
      // Evict oldest
      const oldV = this.buffer[this.tail * 2 + 1]
      if (Number.isFinite(oldV)) {
        if (oldV <= this._min || oldV >= this._max) {
          this._needRecompute = true
        }
      }
      this.tail = (this.tail + 1) % this.capacity
    } else {
      this.count++
    }
    this.buffer[idx] = t
    this.buffer[idx + 1] = v
    this.head = (this.head + 1) % this.capacity

    if (Number.isFinite(v)) {
      if (v < this._min) this._min = v
      if (v > this._max) this._max = v
    }
    if (this._needRecompute) {
      this._needRecompute = false
      this.recomputeStats()
    }
  }

  private _needRecompute = false

  toArray(): { t: number; y: number }[] {
    const result: { t: number; y: number }[] = new Array(this.count)
    for (let i = 0; i < this.count; i++) {
      const idx = ((this.tail + i) % this.capacity) * 2
      result[i] = { t: this.buffer[idx], y: this.buffer[idx + 1] }
    }
    return result
  }

  latest(): { t: number; y: number } | null {
    if (this.count === 0) return null
    const idx = ((this.head - 1 + this.capacity) % this.capacity) * 2
    return { t: this.buffer[idx], y: this.buffer[idx + 1] }
  }

  recomputeStats(): void {
    this._min = Infinity
    this._max = -Infinity
    for (let i = 0; i < this.count; i++) {
      const idx = ((this.tail + i) % this.capacity) * 2
      const v = this.buffer[idx + 1]
      if (Number.isFinite(v)) {
        if (v < this._min) this._min = v
        if (v > this._max) this._max = v
      }
    }
  }

  clear(): void {
    this.head = 0
    this.tail = 0
    this.count = 0
    this._min = Infinity
    this._max = -Infinity
    this._needRecompute = false
  }

  get min(): number { return this._min }
  get max(): number { return this._max }
}
