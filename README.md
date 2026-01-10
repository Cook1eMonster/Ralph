# Ralph Factory

A production planning system for autonomous AI coding agents. Inspired by [Ralph](https://github.com/snarktank/ralph).

## The Assembly Line Model

```
╔════════════════════════════════════════════════════════════════════╗
║                        FACTORY FLOOR                               ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  [WAREHOUSE]         [ASSEMBLY LINES]           [PRODUCTS]         ║
║  ────────────        ─────────────────          ──────────         ║
║  │ Database │   ──►  │ Clinical App  │   ──►   ☑ Login form       ║
║  │ Auth     │   ──►  │ Patient Portal│   ──►   ☐ Vitals card      ║
║  │ API      │   ──►  │ OR Scheduling │   ──►   ☐ Schedule grid    ║
║  │ Shared   │   ──►  │ Integrations  │   ──►   ☐ FHIR parser      ║
║  └──────────┘        └───────────────┘         └──────────┘        ║
║                                                                    ║
║  Parts & materials   Organized workflows       Shipped to users    ║
║  (dependencies)      (feature modules)         (~100k token tasks) ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
```

**Key concepts:**
- **WAREHOUSE** = Core infrastructure everything depends on (database, auth, API framework, shared libs)
- **ASSEMBLY LINES** = Organized workflows for building features (clinical, patient portal, scheduling)
- **PRODUCTS** = Shippable units of work (~100k tokens, single deliverable)

**Workflow:**
```
tree.json          Your production plan
    │
    ▼
┌──────────┐      ┌──────────┐      ┌──────────┐
│ estimate │─────▶│ /factory │─────▶│   next   │
└──────────┘      └──────────┘      └──────────┘
     │                 │                  │
     │    Claude       │    Agent         │
     │    plans        │    builds        │
     │                 │                  ▼
     │                 │            ┌──────────┐
     │                 │            │   done   │
     │                 │            └──────────┘
     │                 │                  │
     └─────────────────┴──────────────────┘
                      loop
```

## Quick Start

### Step 1: Initialize the Factory

```bash
cd ralph-tree
python ralph_tree.py init
```

This creates:
- `tree.json` - Your production plan (starts with template)
- `requirements.md` - Your project goals and constraints
- `config.json` - Agent settings

### Step 2: Define Your Orders

Edit `requirements.md` with your project goals:

```markdown
# Requirements

## Scale
- 10 tenants, 200 concurrent users

## Priorities
- Ship fast, keep it simple
- Patient safety first

## Backlog (build these)
- Patient assessment workflow
- OR scheduling integration
- FHIR data import

## Cancelled (skip these)
- Complex monitoring (Prometheus, Grafana)
- Microservices architecture
- Features not needed for MVP
```

### Step 3: Build the Production Plan

From Claude Code (must be in project root):

```
/factory
```

Claude will:
1. Read `CLAUDE.md` and `requirements.md`
2. Explore the codebase to see what's built
3. Populate `tree.json` with warehouse, assembly lines, and products
4. Mark existing code as "shipped", planned features as "backlog"

### Step 4: Work the Line

```bash
python ralph_tree.py status      # See the factory floor
python ralph_tree.py next        # Grab next product from backlog
# Claude builds the product...
python ralph_tree.py validate    # QA check before shipping
python ralph_tree.py done        # Ship it
```

## Production Plan Structure

```json
{
  "name": "AnesPreOp",
  "context": "Pre-operative assessment system",
  "children": [
    {
      "name": "Warehouse: Core Infrastructure",
      "context": "Stocked parts that all assembly lines depend on",
      "children": [
        {
          "name": "Database & Models",
          "children": [
            {"name": "PostgreSQL setup with pgvector", "status": "done"}
          ]
        }
      ]
    },
    {
      "name": "Line: Clinical Workflow",
      "context": "Assembly line for clinical staff features",
      "children": [
        {
          "name": "Patient Assessment Station",
          "children": [
            {
              "name": "Add vital signs validation to PatientForm",
              "spec": "Validate BP, HR, SpO2. Show inline errors. Use FormField pattern.",
              "read_first": ["src/components/FormField.tsx"],
              "files": ["src/components/VitalsForm.tsx"],
              "acceptance": ["pnpm typecheck", "pnpm test"],
              "status": "pending"
            }
          ]
        }
      ]
    }
  ]
}
```

### Terminology

| Term | Meaning |
|------|---------|
| Warehouse | Core infrastructure (database, auth, API, shared libs) |
| Assembly Line | Feature module (clinical app, patient portal, integrations) |
| Station | Sub-area within a line (patient assessment, scheduling) |
| Product | Single shippable task (~100k tokens) |
| Shipped | Product is complete (code exists, tests pass) |
| Backlog | Product not started |
| On the Line | Product in progress |
| Blocked | Product waiting on dependency |

### Product Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Clear deliverable description |
| `status` | Yes | `done` / `pending` / `in-progress` / `blocked` |
| `spec` | Recommended | 2-3 sentences locking the build requirements |
| `read_first` | Recommended | Reference files to read before building |
| `files` | Optional | Files to create/modify |
| `acceptance` | Recommended | QA commands to run before shipping |

## Session Coherence

Prevent Claude from "forgetting" patterns across sessions:

### Spec Field
Lock product intent with 2-3 sentences:

```json
{
  "name": "Add patient vitals component",
  "spec": "Create VitalsCard showing BP, HR, SpO2. Use existing PatientCard layout pattern. Connect to /api/v1/patients/{id}/vitals endpoint.",
  "status": "pending"
}
```

### Read First Field
Ensure Claude reads existing code before building:

```json
{
  "name": "Add scheduling endpoint",
  "read_first": [
    "src/api/patients.ts",
    "src/models/appointment.ts"
  ],
  "files": ["src/api/scheduling.ts"],
  "status": "pending"
}
```

### Validate Command
QA loop before shipping:

```bash
$ python ralph_tree.py validate

============================================================
VALIDATING: Add patient vitals component
============================================================

$ pnpm typecheck
  ✓ PASSED
$ pnpm test
  ✓ PASSED

============================================================
✓ ALL CHECKS PASSED

Now run code-simplifier before shipping:
  "Use code-simplifier to review and simplify the code I just wrote"

Then ship:
  python ralph_tree.py done
============================================================
```

## Product Sizing

Target ~100k tokens per product:

```
100k tokens ~=
  - ~400 lines of code changes
  - 2-4 files touched
  - 15-25 tool calls
  - Single, shippable outcome
```

**Good products:**
- "Add email validation to LoginForm with error display"
- "Create PatientCard component with name and status"
- "Write unit tests for useAuth hook"

**Too big (split these):**
- "Build complete auth flow" → Split into login, password reset, session management
- "Implement dashboard with all widgets" → Split by widget

**Too small (bundle these):**
- "Fix typo in button" → Bundle with related UI polish

## Token Estimation

```bash
$ python ralph_tree.py estimate

Status   Util | Cmplx  | Product
----------------------------------------------------------------------
[OK  ]  32.5% | low    | Create LoginForm component with validation
[OK  ]  45.2% | medium | Add Firebase auth integration
[OVER] 125.0% | high   | Build complete dashboard with all widgets
```

Products marked `[OVER]` should be split into smaller units.

## Local AI Context (Optional)

Use your GPU to index the codebase and get smarter suggestions:

### Setup

```bash
# Install dependencies
pip install chromadb ollama sentence-transformers

# Install Ollama (https://ollama.com/download)
# Then pull models:
ollama pull nomic-embed-text        # Embeddings (768 dims)
ollama pull qwen2.5-coder:7b        # Summaries (code-specialized)

# Index your codebase (one-time, ~2 min)
python ralph_context.py index
```

### Usage

```bash
# Search codebase semantically
python ralph_context.py search "patient authentication flow"

# Get AI-suggested read_first files
python ralph_context.py suggest "Add patient scheduling API"

# Sync index after pulling changes
python ralph_tree.py sync

# Auto-enrich all products with read_first
python ralph_tree.py enrich

# Get next product with AI context
python ralph_tree.py next --ai
```

### Architecture

```
Query → nomic-embed-text → ChromaDB → 30 candidates
                                          ↓
                               ms-marco-MiniLM (reranker, CPU)
                                          ↓
                                    Top 10 results
```

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU VRAM | 8GB | 12GB (RTX 3080) |
| System RAM | 16GB | 32GB+ |
| Storage | SSD | NVMe SSD |

## Windows Quick Start

```bash
# One-time setup
setup.bat

# Daily startup (pulls, syncs, shows next product)
start.bat

# Or use the launcher
ralph.bat status
ralph.bat next --ai
ralph.bat done
```

## Parallel Workers

Run multiple Claude instances on different products:

### Batch Mode

```bash
# Assign 4 products to workers
python ralph_tree.py assign 4

# Check worker status
python ralph_tree.py workers

# After all workers complete, merge and ship
python ralph_tree.py merge
python ralph_tree.py done-all
```

### Rolling Pipeline

```bash
# Assign products one at a time
python ralph_tree.py assign-one    # → Worker 1
python ralph_tree.py assign-one    # → Worker 2

# As workers finish, ship and re-assign
python ralph_tree.py done-one 1    # Worker 1 shipped
python ralph_tree.py assign-one 1  # Re-assign Worker 1
```

## Commands Reference

### Core Commands

| Command | Description |
|---------|-------------|
| `init` | Create tree.json, requirements.md, config.json |
| `next` | Show next backlog product with context |
| `next --ai` | Show product with AI-enriched context |
| `done` | Ship current product |
| `validate` | Run QA checks before shipping |
| `status` | Show factory floor status |
| `estimate` | Show token estimates for all backlog products |

### AI Context Commands

| Command | Description |
|---------|-------------|
| `enrich` | Auto-suggest read_first for all backlog products |
| `sync` | Sync index with codebase changes |

### Production Plan Management

| Command | Description |
|---------|-------------|
| `add <path> <json>` | Add product to assembly line |
| `prune <path>` | Remove product/station |

### Parallel Workers

| Command | Description |
|---------|-------------|
| `assign <N>` | Assign N products to workers |
| `workers` | Show worker assignments |
| `merge` | Show merge instructions |
| `done-all` | Ship all assigned products |
| `assign-one [id]` | Assign single product (rolling pipeline) |
| `done-one <id>` | Ship single worker's product |

## MCP Server (Claude Code Integration)

Let Claude search your codebase directly:

### Configure Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "ralph-context": {
      "command": "python",
      "args": ["path/to/ralph_context_mcp.py"],
      "cwd": "path/to/project"
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `codebase_search` | Semantic search |
| `suggest_related_files` | Suggest read_first files |
| `summarize_file` | AI summary of large files |
| `index_status` | Check index health |
| `reindex_codebase` | Rebuild index |

## License

MIT
