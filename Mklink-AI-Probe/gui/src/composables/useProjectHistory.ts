import { ref } from 'vue'
import type { ProjectHistoryEntry, ProjectHistory } from '../types/mklink'
import { useMklinkApi } from './useMklinkApi'

const STORAGE_KEY = 'mklink_recent_projects'

function loadFromStorage(): ProjectHistory {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return { last_project: null, history: [] }
}

function saveToStorage(data: ProjectHistory) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch { /* ignore */ }
}

const history = ref<ProjectHistoryEntry[]>([])
const lastProject = ref<string | null>(null)
const historyLoading = ref(false)
let initialized = false

async function refreshFromBackend() {
  historyLoading.value = true
  try {
    const { getProjectHistory } = useMklinkApi()
    const data = await getProjectHistory()
    history.value = data.history || []
    lastProject.value = data.last_project
    saveToStorage(data)
  } catch {
    const stored = loadFromStorage()
    history.value = stored.history || []
    lastProject.value = stored.last_project
  } finally {
    historyLoading.value = false
  }
}

export function useProjectHistory() {
  if (!initialized) {
    initialized = true
    refreshFromBackend()
  }

  async function addEntry(path: string) {
    try {
      const { addProjectHistory } = useMklinkApi()
      const data = await addProjectHistory(path)
      history.value = data.history || []
      lastProject.value = data.last_project
      saveToStorage(data)
    } catch {
      const stored = loadFromStorage()
      const normalized = path.toLowerCase()
      stored.history = stored.history.filter(e => e.path.toLowerCase() !== normalized)
      stored.history.unshift({
        path,
        name: path.replace(/[/\\]+$/, '').split(/[/\\]/).pop() || path,
        last_used: new Date().toISOString(),
      })
      stored.history = stored.history.slice(0, 10)
      stored.last_project = path
      history.value = stored.history
      lastProject.value = stored.last_project
      saveToStorage(stored)
    }
  }

  async function removeEntry(path: string) {
    try {
      const { removeProjectHistory } = useMklinkApi()
      const data = await removeProjectHistory(path)
      history.value = data.history || []
      lastProject.value = data.last_project
      saveToStorage(data)
    } catch {
      const stored = loadFromStorage()
      const normalized = path.toLowerCase()
      stored.history = stored.history.filter(e => e.path.toLowerCase() !== normalized)
      if ((stored.last_project || '').toLowerCase() === normalized) {
        stored.last_project = stored.history[0]?.path || null
      }
      history.value = stored.history
      lastProject.value = stored.last_project
      saveToStorage(stored)
    }
  }

  function filteredEntries(query: string): ProjectHistoryEntry[] {
    if (!query) return history.value
    const q = query.toLowerCase()
    return history.value.filter(
      e => e.path.toLowerCase().includes(q) || e.name.toLowerCase().includes(q)
    )
  }

  return {
    history,
    lastProject,
    historyLoading,
    refreshFromBackend,
    addEntry,
    removeEntry,
    filteredEntries,
  }
}
