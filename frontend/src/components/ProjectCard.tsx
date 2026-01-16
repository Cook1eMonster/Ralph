import { Link } from 'react-router-dom'
import { ProjectSummary } from '../api/client'

interface ProjectCardProps {
  project: ProjectSummary;
}

export default function ProjectCard({ project }: ProjectCardProps) {
  const stats = project.stats
  const progress = stats ? Math.round((stats.done / Math.max(stats.total, 1)) * 100) : 0

  return (
    <Link
      to={`/project/${project.id}`}
      className="block bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-blue-500 transition-colors"
    >
      <h3 className="text-lg font-semibold text-white mb-2">{project.name}</h3>
      <p className="text-sm text-gray-400 mb-3 truncate">{project.path}</p>

      {stats && (
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Progress</span>
            <span className="text-white">{stats.done}/{stats.total}</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className="bg-green-500 h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex gap-4 text-xs">
            {stats.pending > 0 && (
              <span className="text-yellow-400">{stats.pending} pending</span>
            )}
            {stats.in_progress > 0 && (
              <span className="text-blue-400">{stats.in_progress} in progress</span>
            )}
            {stats.blocked > 0 && (
              <span className="text-red-400">{stats.blocked} blocked</span>
            )}
          </div>
        </div>
      )}

      {project.github_url && (
        <div className="mt-3 text-xs text-gray-500 truncate">
          {project.github_url}
        </div>
      )}
    </Link>
  )
}
