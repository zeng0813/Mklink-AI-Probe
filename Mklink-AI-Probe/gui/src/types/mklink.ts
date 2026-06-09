export interface PortInfo {
  device: string
  description: string
  manufacturer: string
  vid: number | null
  pid: number | null
}

export interface McuProfile {
  key: string
  name: string
  [k: string]: unknown
}

export interface ProjectConfig {
  com_port?: string
  mcu_key?: string
  swd_clock?: string
}

export interface ProjectInfo {
  hex_path?: string
  map_path?: string
  flm_path?: string
  flm_name?: string
  flash_base?: string
  axf_path?: string
}

export interface RttConfig {
  rtt_addr?: string
  /** RTT 控制块存储方式：0 = 动态搜寻（默认），1 = 静态编译（C 宏固定地址） */
  rtt_storage_mode?: 0 | 1
  search_size?: number
  channel?: number
  autostart?: boolean
  integrated?: boolean
  [k: string]: unknown
}

export interface ConfigStatus {
  is_valid: boolean
  has_config: boolean
  has_project: boolean
  has_rtt_config: boolean
  errors: string[]
  warnings: string[]
  flm_on_microkeen: boolean
}

export interface AxlStatus {
  loaded: boolean
  axf_path?: string | null
  variable_count?: number
  struct_count?: number
  enum_count?: number
  error?: string
}

export interface DeviceStatus {
  connected: boolean
  state: string
  mcu: string | null
  idcode: string | null
  port: string | null
  axf: AxlStatus
}

export interface MicrokeenInfo {
  disk_path: string | null
  flm_dir: string | null
  available: boolean
}

export interface ConnectRequest {
  port?: string
  axf?: string
  mcu?: string
}

export interface FlashRequest {
  firmware: string
  verify?: boolean
  reset_after?: boolean
}

export interface JsonRpcRequest {
  jsonrpc: '2.0'
  method: string
  params?: Record<string, unknown>
  id?: number | string
  token?: string
}

export interface JsonRpcResponse {
  jsonrpc: '2.0'
  result?: unknown
  error?: { code: number; message: string }
  id: number | string | null
}

export type DashboardType = 'rtt' | 'serial' | 'modbus' | 'superwatch' | 'vofa'

export interface DashboardInfo {
  running: boolean
  url: string | null
}

export interface DashboardStatus {
  [key: string]: DashboardInfo
}

// SSE data point
export interface DataPoint {
  _t?: number
  _event?: string
  [channel: string]: number | string | object | undefined
}

// HardFault detail
export interface HardFaultDetail {
  fault: boolean
  cfsr?: number
  hfsr?: number
  cfsr_flags?: string[]
  hfsr_flags?: string[]
  stack_frame?: Record<string, number> | null
  source_locations?: Record<string, string> | null
  summary?: string
}

// Core registers
export interface CoreRegisters {
  [name: string]: number
}

// Symbol search result
export interface SymbolEntry {
  name: string
  address: number | string | null
  type: string
  size: number
}

// Symbol type info
export interface SymbolTypeInfo {
  name: string
  found: boolean
  type?: string
  size?: number
  address?: number | string | null
  members?: unknown[]
}

// Memory read result
export interface MemoryReadResult {
  address: string
  size: number
  data_base64: string
  data_hex: string
}

// Serial monitor event
export interface SerialEvent {
  event: string
  timestamp?: string
  port?: string
  direction?: 'RX' | 'TX'
  raw_hex?: string
  ascii?: string
  fields?: Record<string, { value: string; unit: string }>
  crc_valid?: boolean | null
}

// Modbus register snapshot
export interface ModbusRegisterValue {
  value: number
  name: string
  type: string
}

export interface ModbusSnapshot {
  _t: number
  registers: Record<number, ModbusRegisterValue>
}

// Project history entry
export interface ProjectHistoryEntry {
  path: string
  name: string
  last_used: string
}

// Full project history
export interface ProjectHistory {
  last_project: string | null
  history: ProjectHistoryEntry[]
}

// 探针自身固件版本检查
export interface FirmwareInfo {
  name: string
  version: string
  model: 'V3' | 'V4'
  path: string
}

export type ProbeFirmwareCheckStatus =
  | 'ok'
  | 'upgrade_required'
  | 'no_firmware_dir'
  | 'skipped'

export interface ProbeFirmwareCheck {
  status: ProbeFirmwareCheckStatus
  current_version: string | null
  min_required_version: string | null
  recommended_uf2: FirmwareInfo | null
  all_uf2s: FirmwareInfo[]
  firmware_dir: string | null
  instructions: string
}
