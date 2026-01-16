const API_BASE = '/api';

export interface FolderEntry {
  name: string;
  path: string;
  is_dir: boolean;
  children?: FolderEntry[];
}

export interface TreeStats {
  total: number;
  done: number;
  pending: number;
  in_progress: number;
  blocked: number;
}

export interface ProjectSummary {
  id: string;
  name: string;
  path: string;
  github_url?: string;
  stats?: TreeStats;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  github_url?: string;
  target_tokens: number;
  venv_path?: string;
}

export interface GitSyncStatus {
  is_git_repo: boolean;
  has_remote: boolean;
  was_behind: boolean;
  pulled: boolean;
  commits_pulled: number;
  error?: string;
}

export interface IndexStatus {
  indexed: number;
  updated: number;
  skipped: number;
  errors: number;
  total_chunks: number;
  error_message?: string;
}

export interface LaunchResponse {
  script_path: string;
  command: string;
  git_sync?: GitSyncStatus;
  index_status?: IndexStatus;
}

export interface TaskNode {
  name: string;
  status: 'pending' | 'in-progress' | 'done' | 'blocked';
  spec?: string;
  context?: string;
  read_first: string[];
  files: string[];
  acceptance: string[];
  children: TaskNode[];
}

export interface Tree {
  name: string;
  context: string;
  children: TaskNode[];
}

export interface TreeResponse {
  tree: Tree;
  stats: TreeStats;
}

export interface TokenEstimate {
  base_overhead: number;
  context_tokens: number;
  task_tokens: number;
  file_reads: number;
  tool_calls: number;
  buffer: number;
  total: number;
  target: number;
  fits: boolean;
  utilization: number;
  complexity: 'low' | 'medium' | 'high';
}

export interface TaskWithPath {
  task: TaskNode;
  path: string[];
}

export interface NextTaskResponse {
  task?: TaskWithPath;
  context: string;
  estimate?: TokenEstimate;
  prompt: string;
}

export interface Worker {
  id: number;
  branch: string;
  task: string;
  path: string;
  status: 'assigned' | 'in-progress' | 'done';
}

export interface WorkerList {
  workers: Worker[];
}

export interface ValidationResult {
  success: boolean;
  command: string;
  stdout: string;
  stderr: string;
  return_code: number;
}

export interface HealingResponse {
  success: boolean;
  attempts: number;
  file_fixed?: string;
  validations: ValidationResult[];
  error?: string;
}

// API Client
export const api = {
  // Filesystem
  browse: async (path?: string): Promise<FolderEntry[]> => {
    const url = path ? `${API_BASE}/browse?path=${encodeURIComponent(path)}` : `${API_BASE}/browse`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to browse');
    return res.json();
  },

  // Projects
  listProjects: async (): Promise<ProjectSummary[]> => {
    const res = await fetch(`${API_BASE}/projects`);
    if (!res.ok) throw new Error('Failed to list projects');
    return res.json();
  },

  createProject: async (data: { name: string; path: string; github_url?: string; venv_path?: string }): Promise<Project> => {
    const res = await fetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to create project');
    return res.json();
  },

  getProject: async (id: string): Promise<Project> => {
    const res = await fetch(`${API_BASE}/projects/${id}`);
    if (!res.ok) throw new Error('Project not found');
    return res.json();
  },

  deleteProject: async (id: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/projects/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete project');
  },

  // Tree
  getTree: async (projectId: string): Promise<TreeResponse> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/tree`);
    if (!res.ok) throw new Error('Failed to get tree');
    return res.json();
  },

  updateTree: async (projectId: string, tree: Tree): Promise<TreeResponse> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/tree`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tree),
    });
    if (!res.ok) throw new Error('Failed to update tree');
    return res.json();
  },

  generatePlan: async (projectId: string): Promise<TreeResponse> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/generate-plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ use_ai: true }),
    });
    if (!res.ok) throw new Error('Failed to generate plan');
    return res.json();
  },

  // Tasks
  getNextTask: async (projectId: string): Promise<NextTaskResponse> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/tasks/next`);
    if (!res.ok) throw new Error('Failed to get next task');
    return res.json();
  },

  updateTaskStatus: async (projectId: string, taskPath: string, status: string): Promise<TreeResponse> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/tasks/${taskPath}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error('Failed to update task status');
    return res.json();
  },

  // Workers
  getWorkers: async (projectId: string): Promise<WorkerList> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/workers`);
    if (!res.ok) throw new Error('Failed to get workers');
    return res.json();
  },

  assignWorkers: async (projectId: string, count: number): Promise<WorkerList> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/workers/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ count }),
    });
    if (!res.ok) throw new Error('Failed to assign workers');
    return res.json();
  },

  completeWorker: async (projectId: string, workerId: number): Promise<WorkerList> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/workers/${workerId}/done`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to complete worker');
    return res.json();
  },

  // Launch
  launchProject: async (projectId: string): Promise<LaunchResponse> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/launch`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to launch project');
    return res.json();
  },

  updateProject: async (projectId: string, data: Partial<Project>): Promise<Project> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update project');
    return res.json();
  },

  // Self-Healing
  healTask: async (projectId: string, taskPath: string, maxAttempts: number = 3): Promise<HealingResponse> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/heal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_path: taskPath, max_attempts: maxAttempts }),
    });
    if (!res.ok) throw new Error('Failed to heal task');
    return res.json();
  },

  validateTask: async (projectId: string, taskPath: string): Promise<{ success: boolean; validations: ValidationResult[] }> => {
    const res = await fetch(`${API_BASE}/projects/${projectId}/tasks/${taskPath}/validate`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to validate task');
    return res.json();
  },
};
