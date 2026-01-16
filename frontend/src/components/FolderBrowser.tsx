import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, FolderEntry } from '../api/client'

interface FolderBrowserProps {
  onSelect: (path: string) => void;
  initialPath?: string;
}

function FolderItem({
  entry,
  onSelect,
  selectedPath
}: {
  entry: FolderEntry;
  onSelect: (path: string) => void;
  selectedPath: string;
}) {
  const [expanded, setExpanded] = useState(false)
  const isSelected = entry.path === selectedPath

  const { data: children } = useQuery({
    queryKey: ['browse', entry.path],
    queryFn: () => api.browse(entry.path),
    enabled: expanded && entry.is_dir,
  })

  if (!entry.is_dir) return null

  return (
    <div className="ml-2">
      <div
        className={`flex items-center gap-2 py-1 px-2 rounded cursor-pointer hover:bg-gray-700 ${
          isSelected ? 'bg-blue-900 text-blue-200' : ''
        }`}
        onClick={() => {
          setExpanded(!expanded)
          onSelect(entry.path)
        }}
      >
        <span className="text-gray-400">
          {expanded ? '📂' : '📁'}
        </span>
        <span className="text-sm">{entry.name}</span>
      </div>
      {expanded && children && (
        <div className="ml-4 border-l border-gray-700">
          {children.map((child) => (
            <FolderItem
              key={child.path}
              entry={child}
              onSelect={onSelect}
              selectedPath={selectedPath}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function FolderBrowser({ onSelect, initialPath }: FolderBrowserProps) {
  const [selectedPath, setSelectedPath] = useState(initialPath || '')
  const [inputPath, setInputPath] = useState(initialPath || '')

  const { data: roots, isLoading } = useQuery({
    queryKey: ['browse', null],
    queryFn: () => api.browse(),
  })

  const handleSelect = (path: string) => {
    setSelectedPath(path)
    setInputPath(path)
    onSelect(path)
  }

  const handleInputSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (inputPath) {
      setSelectedPath(inputPath)
      onSelect(inputPath)
    }
  }

  if (isLoading) {
    return <div className="text-gray-400">Loading...</div>
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleInputSubmit} className="flex gap-2">
        <input
          type="text"
          value={inputPath}
          onChange={(e) => setInputPath(e.target.value)}
          placeholder="Enter path or browse below"
          className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
        />
        <button
          type="submit"
          className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm"
        >
          Go
        </button>
      </form>

      <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 max-h-80 overflow-auto">
        {roots?.map((entry) => (
          <FolderItem
            key={entry.path}
            entry={entry}
            onSelect={handleSelect}
            selectedPath={selectedPath}
          />
        ))}
      </div>

      {selectedPath && (
        <div className="text-sm text-gray-400">
          Selected: <span className="text-blue-400">{selectedPath}</span>
        </div>
      )}
    </div>
  )
}
