# Ralph - Dynamic Task Tree for Autonomous AI Agents

## Overview

Ralph is a production planning system for autonomous AI agents. It manages hierarchical task trees where:
- Leaf tasks are executed by AI agents (max ~100k tokens each)
- Branches dynamically spawn/prune based on requirements
- Context flows from parent to child nodes
- Fresh subagents execute tasks with isolated context to prevent "context rot"

## Quick Start

```bash
# Initialize a new project
python ralph_tree.py init

# View next task
python ralph_tree.py next

# Execute task with fresh subagent
python ralph_tree.py execute --verbose

# Mark task complete
python ralph_tree.py done
```

## Project Structure

```
ralph_tree.py          # Main CLI - task tree management and subagent execution
ralph_context.py       # Local AI context engine (Ollama + ChromaDB)
ralph_context_mcp.py   # MCP server exposing semantic search to Claude
tree.json              # Task tree definition
requirements.md        # Project requirements
config.json            # Agent configuration
workers.json           # Parallel worker assignments
.claude/commands/      # Slash commands for Claude Code
```

## Core Commands

### Task Management
```bash
python ralph_tree.py init          # Create tree.json, requirements.md, config.json
python ralph_tree.py next          # Show next pending task
python ralph_tree.py next --ai     # Show task with AI-enriched context
python ralph_tree.py done          # Mark current task as done
python ralph_tree.py validate      # Run acceptance checks
python ralph_tree.py status        # Show tree progress
python ralph_tree.py estimate      # Show token estimates
```

### Autonomous Execution (spawns fresh Claude subagents)
```bash
python ralph_tree.py execute              # Execute next task
python ralph_tree.py execute --verbose    # Stream output in real-time
python ralph_tree.py execute --auto       # Auto-validate and mark done
python ralph_tree.py execute --merge      # Auto-merge branch to main
python ralph_tree.py execute --retries 5  # Max fix attempts (default: 3)
python ralph_tree.py execute-parallel 4   # Execute 4 tasks in parallel
python ralph_tree.py execute-parallel --merge  # Auto-merge all completed
```

### Auto-Fix Loop
When validation fails, Ralph automatically spawns fix subagents:
1. Subagent completes task
2. Validation runs (acceptance criteria)
3. If FAIL: spawn fix subagent with error output
4. Fix subagent reads errors, makes minimal fixes, commits
5. Re-run validation
6. Repeat up to `--retries` times (default: 3)
7. If still failing after max retries, task stays pending for manual fix

### Parallel Workers (manual orchestration)
```bash
python ralph_tree.py assign 4      # Assign 4 tasks to workers
python ralph_tree.py workers       # Show current worker assignments
python ralph_tree.py merge         # Show merge instructions
python ralph_tree.py done-all      # Mark all assigned tasks done
python ralph_tree.py assign-one    # Rolling pipeline - assign one task
python ralph_tree.py done-one 1    # Complete single worker
```

### AI Context (requires Ollama + ChromaDB)
```bash
python ralph_context.py index      # Index codebase
python ralph_context.py search "auth login"  # Semantic search
python ralph_tree.py sync          # Sync index with codebase changes
python ralph_tree.py enrich        # Auto-suggest read_first files
```

## Functional Slices

Functional slices organize work into vertical feature slices - each slice delivers user-visible value by including backend, frontend, and tests together. Slices are completed one at a time, with validation and strategic review between slices.

### Why Slices?
- **Manageable scope**: Each slice is small enough to complete thoroughly
- **Validated incrementally**: Integration tests run after each slice
- **Strategic checkpoints**: Review and adjust before proceeding
- **Prevents context rot**: Fresh perspective between slices

### Slice Commands
```bash
python ralph_tree.py slices           # Show all slices and progress
python ralph_tree.py slice-validate   # Run slice integration tests
python ralph_tree.py slice-review     # Generate 5-10 strategic questions
python ralph_tree.py slice-done       # Mark slice complete, proceed to next
```

### Slice Workflow
```
┌─────────────────────────────────────────────────────────────────┐
│  SLICE 1: User Auth           SLICE 2: Patient CRUD            │
│  ───────────────────          ──────────────────────            │
│  [x] User model               [ ] Patient model                 │
│  [x] Login endpoint           [ ] CRUD endpoints                │
│  [x] Login form               [ ] List/Detail views             │
│  ───────────────────          ──────────────────────            │
│  ▶ slice-validate             (locked until Slice 1 done)       │
│  ▶ slice-review                                                 │
│  ▶ slice-done                                                   │
└─────────────────────────────────────────────────────────────────┘
```

1. Complete all tasks in current slice (`next` only returns tasks from current slice)
2. Run `slice-validate` to run integration tests
3. Run `slice-review` to generate strategic review questions
4. Discuss with user: obstacles, strategy changes, scope adjustments
5. Run `slice-done` to mark complete and proceed to next slice

### Slice Fields
| Field | Description |
|-------|-------------|
| `slice` | `true` (marks node as a functional slice) |
| `order` | Execution order (lower = earlier) |
| `validation` | Slice-level integration test commands |
| `dependencies` | Other slices this depends on (for reference) |

### Example tree.json with Slices
```json
{
  "name": "AnesPreOp",
  "context": "Pre-operative assessment system",
  "children": [
    {
      "name": "Slice 1: User Authentication",
      "slice": true,
      "order": 1,
      "validation": ["pytest tests/auth/", "npm run test:auth"],
      "context": "JWT-based auth with refresh tokens",
      "children": [
        {
          "name": "Create User model with email, password_hash",
          "files": ["app/models/user.py"],
          "acceptance": ["pytest", "mypy app/"],
          "status": "pending"
        },
        {
          "name": "Add /api/auth/login endpoint",
          "files": ["app/api/auth.py"],
          "read_first": ["app/models/user.py"],
          "acceptance": ["pytest tests/auth/"],
          "status": "pending"
        }
      ]
    },
    {
      "name": "Slice 2: Patient CRUD",
      "slice": true,
      "order": 2,
      "validation": ["pytest tests/patients/"],
      "dependencies": ["Slice 1: User Authentication"],
      "children": [
        {"name": "Create Patient model", "status": "pending"},
        {"name": "Add patient CRUD endpoints", "status": "pending"}
      ]
    }
  ]
}
```

### Slice Review Questions
When `slice-review` is run, Claude asks strategic questions:

1. **Progress**: Did implementation match intent? Any deviations?
2. **Technical Debt**: What shortcuts were taken?
3. **Edge Cases**: Missing error handling or validation?
4. **Obstacles**: What unexpected challenges came up?
5. **Blockers**: Anything blocking the next slice?
6. **Strategy**: Should upcoming tasks be split, merged, pruned, or reordered?
7. **Criteria**: Are acceptance criteria still appropriate?
8. **Clarification**: Any requirements needing clarification?
9. **Scope**: New features to add or remove?
10. **Ready?**: Proceed to next slice?

## Tree Structure

Tasks are organized hierarchically in `tree.json`:

```json
{
  "name": "Project",
  "context": "Project-level context",
  "children": [
    {
      "name": "Feature",
      "context": "Feature context inherited by children",
      "children": [
        {
          "name": "Atomic task description",
          "spec": "Brief spec locking intent (2-3 sentences)",
          "read_first": ["src/patterns.py"],
          "files": ["src/new_feature.py"],
          "acceptance": ["pytest", "ruff check"],
          "status": "pending"
        }
      ]
    }
  ]
}
```

### Task Fields
| Field | Description |
|-------|-------------|
| `name` | Task description (required) |
| `status` | pending / in-progress / done / blocked |
| `spec` | Brief spec to lock intent (2-3 sentences) |
| `read_first` | Files to read before coding (ensures consistency) |
| `files` | Files to create/modify |
| `acceptance` | Commands to verify completion (QA loop) |
| `context` | Additional context inherited by children |

## Slash Commands

Available via `/ralph-*` in Claude Code:

| Command | Description |
|---------|-------------|
| `/ralph-next` | Get next task |
| `/ralph-done` | Mark task complete |
| `/ralph-status` | Show progress |
| `/ralph-validate` | Run acceptance checks |
| `/ralph-execute` | Execute with subagent |
| `/ralph-plan` | Governance prompt |
| `/ralph-sync` | Sync codebase index |
| `/ralph-workers` | Show worker assignments |
| `/ralph-estimate` | Show token estimates |
| `/ralph-debug` | Troubleshooting guide |

## MCP Server

The MCP server (`ralph_context_mcp.py`) exposes semantic search tools to Claude:

```json
{
  "mcpServers": {
    "ralph-context": {
      "command": "python",
      "args": ["ralph_context_mcp.py"],
      "cwd": "/path/to/project"
    }
  }
}
```

### Available MCP Tools
- `codebase_search` - Semantic codebase search
- `suggest_related_files` - Find files related to a task
- `summarize_file` - AI-generated file summaries
- `index_status` - Check index status
- `reindex_codebase` - Re-index changed files

## Token Budget

Ralph targets ~100k tokens per task:
- `BASE_OVERHEAD`: 15,000 tokens (system prompt, tools)
- `TOKENS_PER_FILE`: 2,500 tokens per file read
- `TOKENS_PER_TOOL_CALL`: 500 tokens overhead

Use `python ralph_tree.py estimate` to check task token usage.

## AI Context Setup (Optional)

For semantic search and file suggestions:

```bash
pip install chromadb ollama
ollama pull nomic-embed-text
ollama pull qwen2.5-coder:7b
python ralph_context.py index
```

## Workflow

### Standard Flow
```bash
python ralph_tree.py next       # Get task
# Read read_first files, implement to spec
python ralph_tree.py validate   # Run acceptance checks
python ralph_tree.py done       # Mark complete
```

### Autonomous Flow
```bash
python ralph_tree.py execute --auto --merge
# Subagent: reads files, implements, commits, validates, merges
```

### Parallel Flow
```bash
python ralph_tree.py execute-parallel 4 --merge
# 4 subagents work concurrently on separate branches
```

## Configuration

`config.json`:
```json
{
  "agent": "claude",
  "agent_cmd": "claude -p",
  "target_tokens": 100000
}
```

## Code Conventions

- Python 3.10+ with type hints
- Functions use snake_case
- CLI commands use hyphen-case
- JSON files use camelCase for tree fields
- All files use UTF-8 encoding
