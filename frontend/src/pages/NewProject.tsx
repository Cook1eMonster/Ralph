import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import FolderBrowser from '../components/FolderBrowser'

export default function NewProject() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [githubUrl, setGithubUrl] = useState('')
  const [venvPath, setVenvPath] = useState('')

  const createProject = useMutation({
    mutationFn: () =>
      api.createProject({
        name: name || path.split(/[/\\]/).pop() || 'Project',
        path,
        github_url: githubUrl || undefined,
        venv_path: venvPath || undefined,
      }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/project/${project.id}`)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!path) return
    createProject.mutate()
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h2 className="text-xl font-bold text-white">New Project</h2>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Project Folder
          </label>
          <FolderBrowser onSelect={setPath} />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Project Name (optional)
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={path.split(/[/\\]/).pop() || 'Enter project name'}
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            GitHub URL (optional)
          </label>
          <input
            type="text"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            placeholder="https://github.com/user/repo"
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Python Venv Path (optional, auto-detected)
          </label>
          <input
            type="text"
            value={venvPath}
            onChange={(e) => setVenvPath(e.target.value)}
            placeholder="venv, .venv, or absolute path"
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 focus:outline-none focus:border-blue-500"
          />
          <p className="text-xs text-gray-500 mt-1">
            Leave empty to auto-detect. Ralph will activate this venv when launching.
          </p>
        </div>

        <div className="flex gap-4">
          <button
            type="submit"
            disabled={!path || createProject.isPending}
            className="bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 disabled:cursor-not-allowed px-6 py-2 rounded font-medium"
          >
            {createProject.isPending ? 'Creating...' : 'Create Project'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="bg-gray-700 hover:bg-gray-600 px-6 py-2 rounded"
          >
            Cancel
          </button>
        </div>

        {createProject.isError && (
          <div className="text-red-400 text-sm">
            Failed to create project. Please try again.
          </div>
        )}
      </form>
    </div>
  )
}
