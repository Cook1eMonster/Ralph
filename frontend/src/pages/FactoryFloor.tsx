import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, LaunchResponse } from '../api/client'
import TaskBoard from '../components/TaskBoard'

export default function FactoryFloor() {
  const { projectId } = useParams<{ projectId: string }>()
  const queryClient = useQueryClient()
  const [launchInfo, setLaunchInfo] = useState<LaunchResponse | null>(null)

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProject(projectId!),
    enabled: !!projectId,
  })

  const { data: treeData, isLoading } = useQuery({
    queryKey: ['tree', projectId],
    queryFn: () => api.getTree(projectId!),
    enabled: !!projectId,
  })

  const { data: nextTask } = useQuery({
    queryKey: ['nextTask', projectId],
    queryFn: () => api.getNextTask(projectId!),
    enabled: !!projectId,
  })

  const generatePlan = useMutation({
    mutationFn: () => api.generatePlan(projectId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tree', projectId] })
    },
  })

  const launchProject = useMutation({
    mutationFn: () => api.launchProject(projectId!),
    onSuccess: (data) => {
      setLaunchInfo(data)
    },
  })

  if (isLoading) {
    return <div className="text-gray-400">Loading...</div>
  }

  const stats = treeData?.stats
  const progress = stats ? Math.round((stats.done / Math.max(stats.total, 1)) * 100) : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <Link to="/" className="text-gray-400 hover:text-white text-sm mb-2 block">
            &larr; Back to Projects
          </Link>
          <h2 className="text-2xl font-bold text-white">{project?.name}</h2>
          <p className="text-gray-400 text-sm">{project?.path}</p>
        </div>
        <div className="text-right">
          {stats && (
            <div className="mb-2">
              <span className="text-2xl font-bold text-white">{progress}%</span>
              <span className="text-gray-400 ml-2">
                ({stats.done}/{stats.total} tasks)
              </span>
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => launchProject.mutate()}
              disabled={launchProject.isPending}
              className="bg-green-600 hover:bg-green-500 disabled:bg-gray-600 px-4 py-2 rounded text-sm font-medium"
            >
              {launchProject.isPending ? 'Launching...' : 'Launch'}
            </button>
            <button
              onClick={() => generatePlan.mutate()}
              disabled={generatePlan.isPending}
              className="bg-purple-600 hover:bg-purple-500 disabled:bg-gray-600 px-4 py-2 rounded text-sm"
            >
              {generatePlan.isPending ? 'Generating...' : 'Generate Plan'}
            </button>
          </div>
        </div>
      </div>

      {/* Launch Info Modal */}
      {launchInfo && (
        <div className="bg-green-900/50 border border-green-500 rounded-lg p-4">
          <div className="flex justify-between items-start">
            <div className="flex-1">
              <h3 className="font-semibold text-green-400 mb-2">Launch Script Generated</h3>

              {/* Git Sync Status */}
              {launchInfo.git_sync && launchInfo.git_sync.is_git_repo && (
                <div className="mb-3 p-2 bg-gray-900 rounded text-sm">
                  {launchInfo.git_sync.error ? (
                    <span className="text-red-400">
                      Git sync error: {launchInfo.git_sync.error}
                    </span>
                  ) : launchInfo.git_sync.pulled ? (
                    <span className="text-blue-400">
                      Pulled {launchInfo.git_sync.commits_pulled} commit(s) from remote
                    </span>
                  ) : launchInfo.git_sync.was_behind ? (
                    <span className="text-yellow-400">
                      Behind remote by {launchInfo.git_sync.commits_pulled} commit(s)
                    </span>
                  ) : launchInfo.git_sync.has_remote ? (
                    <span className="text-green-400">
                      Up to date with remote
                    </span>
                  ) : (
                    <span className="text-gray-400">
                      No remote configured
                    </span>
                  )}
                </div>
              )}

              {/* Index Status */}
              {launchInfo.index_status && (
                <div className="mb-3 p-2 bg-gray-900 rounded text-sm">
                  {launchInfo.index_status.error_message ? (
                    <span className="text-red-400">
                      Index error: {launchInfo.index_status.error_message}
                    </span>
                  ) : (launchInfo.index_status.indexed > 0 || launchInfo.index_status.updated > 0) ? (
                    <span className="text-purple-400">
                      Indexed: {launchInfo.index_status.indexed} new, {launchInfo.index_status.updated} updated ({launchInfo.index_status.total_chunks} chunks)
                    </span>
                  ) : launchInfo.index_status.total_chunks > 0 ? (
                    <span className="text-green-400">
                      Index up to date ({launchInfo.index_status.total_chunks} chunks)
                    </span>
                  ) : (
                    <span className="text-gray-400">
                      No files indexed (ChromaDB may not be available)
                    </span>
                  )}
                </div>
              )}

              <p className="text-sm text-gray-300 mb-2">
                Run this command in a terminal to start working:
              </p>
              <code className="block bg-gray-900 p-2 rounded text-sm text-green-300 font-mono">
                {launchInfo.script_path}
              </code>
              <p className="text-xs text-gray-500 mt-2">
                Or copy: <code className="text-green-400">{launchInfo.command}</code>
              </p>
            </div>
            <button
              onClick={() => setLaunchInfo(null)}
              className="text-gray-400 hover:text-white ml-4"
            >
              &times;
            </button>
          </div>
        </div>
      )}

      {/* Progress bar */}
      {stats && (
        <div className="w-full bg-gray-700 rounded-full h-3">
          <div
            className="bg-green-500 h-3 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Next task prompt */}
      {nextTask?.task && (
        <div className="bg-gray-800 border border-blue-500 rounded-lg p-4">
          <h3 className="font-semibold text-blue-400 mb-2">Next Task</h3>
          <p className="text-white font-medium">{nextTask.task.task.name}</p>
          {nextTask.task.task.spec && (
            <p className="text-gray-400 text-sm mt-1">{nextTask.task.task.spec}</p>
          )}
          {nextTask.estimate && (
            <div className="mt-2 text-xs text-gray-500">
              ~{nextTask.estimate.total.toLocaleString()} tokens ({nextTask.estimate.utilization}%)
              {' | '}
              Complexity: {nextTask.estimate.complexity}
            </div>
          )}
          <details className="mt-3">
            <summary className="cursor-pointer text-sm text-gray-400 hover:text-white">
              Show full prompt
            </summary>
            <pre className="mt-2 p-3 bg-gray-900 rounded text-xs overflow-auto max-h-60">
              {nextTask.prompt}
            </pre>
          </details>
        </div>
      )}

      {/* Task board */}
      {treeData?.tree && (
        <TaskBoard projectId={projectId!} tree={treeData.tree} />
      )}

      {/* Empty state */}
      {treeData?.tree && treeData.tree.children.length === 0 && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center">
          <h3 className="text-lg font-medium text-white mb-2">No tasks yet</h3>
          <p className="text-gray-400 mb-4">
            Click "Generate Plan" to analyze the codebase and create a factory plan.
          </p>
        </div>
      )}
    </div>
  )
}
