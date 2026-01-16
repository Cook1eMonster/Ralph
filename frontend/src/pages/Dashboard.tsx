import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import ProjectCard from '../components/ProjectCard'

export default function Dashboard() {
  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  })

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold text-white">Projects</h2>
        <Link
          to="/new"
          className="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded text-sm font-medium"
        >
          + New Project
        </Link>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading projects...</div>
      ) : projects?.length === 0 ? (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center">
          <h3 className="text-lg font-medium text-white mb-2">No projects yet</h3>
          <p className="text-gray-400 mb-4">
            Create your first project to start managing tasks.
          </p>
          <Link
            to="/new"
            className="inline-block bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded text-sm font-medium"
          >
            Create Project
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects?.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  )
}
