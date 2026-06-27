export interface SystemViewTaskRuntime {
  id: number
  name: string
  color: string
  runUs: number
  switches: number
  prio?: number
}

export interface SystemViewTaskRow extends SystemViewTaskRuntime {
  pct: number
}

export function computeTaskRows(tasks: SystemViewTaskRuntime[]): SystemViewTaskRow[] {
  const totalRun = tasks.reduce((sum, task) => {
    const run = Number.isFinite(task.runUs) ? Math.max(task.runUs, 0) : 0
    return sum + run
  }, 0)

  return tasks
    .map(task => ({
      ...task,
      pct: totalRun > 0 ? Math.max(task.runUs, 0) / totalRun * 100 : 0,
    }))
    .sort((a, b) => b.pct - a.pct)
}
