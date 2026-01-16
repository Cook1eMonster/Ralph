import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, TaskNode, Tree, HealingResponse } from '../api/client'

interface TaskBoardProps {
  projectId: string;
  tree: Tree;
}

interface TaskCardProps {
  task: TaskNode;
  path: string[];
  projectId: string;
}

function TaskCard({ task, path, projectId }: TaskCardProps) {
  const queryClient = useQueryClient()
  const taskPath = path.join('.')
  const [healResult, setHealResult] = useState<HealingResponse | null>(null)

  const updateStatus = useMutation({
    mutationFn: (status: string) => api.updateTaskStatus(projectId, taskPath, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tree', projectId] })
    },
  })

  const validateTask = useMutation({
    mutationFn: () => api.validateTask(projectId, taskPath),
    onSuccess: (data) => {
      setHealResult({
        success: data.success,
        attempts: 0,
        validations: data.validations,
      })
    },
  })

  const healTask = useMutation({
    mutationFn: () => api.healTask(projectId, taskPath),
    onSuccess: (data) => {
      setHealResult(data)
      if (data.success) {
        queryClient.invalidateQueries({ queryKey: ['tree', projectId] })
      }
    },
  })

  const hasAcceptance = task.acceptance && task.acceptance.length > 0

  const statusColors = {
    pending: 'border-yellow-500 bg-yellow-900/20',
    'in-progress': 'border-blue-500 bg-blue-900/20',
    done: 'border-green-500 bg-green-900/20',
    blocked: 'border-red-500 bg-red-900/20',
  }

  return (
    <div
      className={`p-3 rounded border ${statusColors[task.status]} mb-2`}
    >
      <div className="font-medium text-sm mb-2">{task.name}</div>
      {task.spec && (
        <p className="text-xs text-gray-400 mb-2 line-clamp-2">{task.spec}</p>
      )}

      {/* Healing result display */}
      {healResult && (
        <div className={`text-xs p-2 rounded mb-2 ${healResult.success ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
          <div className="flex justify-between items-center">
            <span>
              {healResult.success ? 'Passed' : 'Failed'}
              {healResult.attempts > 0 && ` (${healResult.attempts} attempts)`}
            </span>
            <button onClick={() => setHealResult(null)} className="text-gray-400 hover:text-white">&times;</button>
          </div>
          {healResult.error && <p className="mt-1">{healResult.error}</p>}
          {healResult.validations.length > 0 && !healResult.success && (
            <details className="mt-1">
              <summary className="cursor-pointer">Validation output</summary>
              <pre className="mt-1 text-xs overflow-auto max-h-32 bg-gray-900 p-1 rounded">
                {healResult.validations.map(v => v.stderr || v.stdout).join('\n')}
              </pre>
            </details>
          )}
        </div>
      )}

      <div className="flex gap-1 flex-wrap">
        {task.status !== 'done' && (
          <button
            onClick={() => updateStatus.mutate('done')}
            className="text-xs bg-green-700 hover:bg-green-600 px-2 py-1 rounded"
          >
            Done
          </button>
        )}
        {task.status === 'pending' && (
          <button
            onClick={() => updateStatus.mutate('in-progress')}
            className="text-xs bg-blue-700 hover:bg-blue-600 px-2 py-1 rounded"
          >
            Start
          </button>
        )}
        {task.status !== 'blocked' && task.status !== 'done' && (
          <button
            onClick={() => updateStatus.mutate('blocked')}
            className="text-xs bg-red-700 hover:bg-red-600 px-2 py-1 rounded"
          >
            Block
          </button>
        )}
        {task.status === 'blocked' && (
          <button
            onClick={() => updateStatus.mutate('pending')}
            className="text-xs bg-yellow-700 hover:bg-yellow-600 px-2 py-1 rounded"
          >
            Unblock
          </button>
        )}
        {/* Validate and Heal buttons - only show if task has acceptance criteria */}
        {hasAcceptance && (
          <>
            <button
              onClick={() => validateTask.mutate()}
              disabled={validateTask.isPending}
              className="text-xs bg-purple-700 hover:bg-purple-600 disabled:bg-gray-600 px-2 py-1 rounded"
            >
              {validateTask.isPending ? '...' : 'Validate'}
            </button>
            <button
              onClick={() => healTask.mutate()}
              disabled={healTask.isPending}
              className="text-xs bg-orange-700 hover:bg-orange-600 disabled:bg-gray-600 px-2 py-1 rounded"
            >
              {healTask.isPending ? 'Healing...' : 'Heal'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}

function collectLeafTasks(
  node: TaskNode,
  path: string[],
  tasks: { task: TaskNode; path: string[] }[]
) {
  const currentPath = [...path, node.name]
  if (node.children.length === 0) {
    tasks.push({ task: node, path: currentPath })
  } else {
    node.children.forEach((child) => collectLeafTasks(child, currentPath, tasks))
  }
}

export default function TaskBoard({ projectId, tree }: TaskBoardProps) {
  const allTasks: { task: TaskNode; path: string[] }[] = []

  tree.children.forEach((child) => {
    collectLeafTasks(child, [tree.name], allTasks)
  })

  const columns = {
    pending: allTasks.filter((t) => t.task.status === 'pending'),
    'in-progress': allTasks.filter((t) => t.task.status === 'in-progress'),
    done: allTasks.filter((t) => t.task.status === 'done'),
    blocked: allTasks.filter((t) => t.task.status === 'blocked'),
  }

  const columnConfig = [
    { key: 'pending', label: 'Pending', color: 'text-yellow-400' },
    { key: 'in-progress', label: 'In Progress', color: 'text-blue-400' },
    { key: 'done', label: 'Done', color: 'text-green-400' },
    { key: 'blocked', label: 'Blocked', color: 'text-red-400' },
  ] as const

  return (
    <div className="grid grid-cols-4 gap-4">
      {columnConfig.map((col) => (
        <div key={col.key} className="bg-gray-800 rounded-lg p-4">
          <h3 className={`font-semibold mb-4 ${col.color}`}>
            {col.label} ({columns[col.key].length})
          </h3>
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {columns[col.key].map(({ task, path }) => (
              <TaskCard
                key={path.join('.')}
                task={task}
                path={path}
                projectId={projectId}
              />
            ))}
            {columns[col.key].length === 0 && (
              <p className="text-gray-500 text-sm italic">No tasks</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
