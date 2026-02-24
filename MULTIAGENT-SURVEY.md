# Multi-Agent Orchestration Design Survey for co-vibe.py

**Date**: 2026-02-24
**Target**: co-vibe.py v1.4.0 (8,297 lines, single-file)
**Goal**: Design proposals to make co-vibe's multi-agent system world-class while maintaining the single-file constraint.

---

## 1. Current State Analysis

### 1.1 Architecture Overview

co-vibe.py implements a **single-file, multi-provider AI coding agent** with the following core classes:

| Class | Lines | Role |
|-------|-------|------|
| `Config` | ~700-1050 | Configuration, strategy selection, API key management |
| `MultiProviderClient` | ~1320-2170 | API routing to Anthropic/OpenAI/Groq with fallback |
| `Agent` | ~6771-7400+ | Main orchestration loop with 3-tier auto-strategy |
| `SubAgentTool` | ~4088-4450 | Autonomous sub-agent with its own tool loop |
| `ParallelAgentTool` | ~4953-5030 | Launches 2-6 sub-agents concurrently |
| `MultiAgentCoordinator` | ~4828-4950 | Thread-based parallel execution engine |
| `Session` | ~5346-5700 | Conversation history, compaction, persistence |
| `TaskCreate/List/Get/Update` | ~3799-4030 | In-memory task tracking (no inter-agent visibility) |

### 1.2 Current Orchestration Strategies

**Strategy tier system** (`Config.STRATEGY_TIER_MAP`):
- `strong` -> Claude Opus 4.6, o3 (complex architecture, hard debugging)
- `balanced` -> Claude Sonnet 4.6, GPT-4o (everyday coding)
- `fast` -> Claude Haiku 4.5, GPT-4o-mini, Groq Llama (simple tasks)
- `auto` -> Heuristic classification based on user input complexity

**Auto-detection** (`Agent._classify_complexity`): Regex-based heuristic that promotes/demotes tier based on text patterns (Japanese and English). Strong patterns include "architect", "refactor", "debug...complex", etc. Fast patterns include short questions, typos, "yes/no".

### 1.3 Current Multi-Agent Capabilities

**What exists**:
1. **SubAgent** - Spawns a sub-agent with its own conversation loop (up to 20 turns), using the sidecar model. Read-only by default, optionally write-capable.
2. **ParallelAgents** - Runs 2-6 SubAgents concurrently via `threading.Thread`. Rate-limit retry (2 retries with jittered backoff). Heartbeat progress display.
3. **Auto-parallel detection** (`Agent._detect_parallel_tasks`) - Regex-based detection of numbered/bulleted lists in user input. Auto-dispatches to ParallelAgents.
4. **Provider fallback** - If one provider returns 429 or error, tries another provider. Health tracking with 60s cooldown.
5. **Context compaction** - Sidecar model summarizes old messages when context hits 70%.

**What is missing**:
1. **No inter-agent communication** - Sub-agents cannot communicate with each other or the parent agent during execution.
2. **No shared memory/blackboard** - Each sub-agent has an isolated conversation. No way to share discoveries.
3. **No task dependency graph** - TaskCreate/Update are in-memory and not visible across sub-agent boundaries.
4. **No dynamic re-planning** - Once tasks are dispatched, they run to completion with no adaptation.
5. **No agent roles/specialization** - All sub-agents use the same generic system prompt.
6. **No result synthesis** - ParallelAgents concatenates results; no intelligent merging.
7. **No learning/feedback loop** - No mechanism to improve orchestration based on past results.
8. **No hierarchical delegation** - Only one level deep (parent -> sub-agent). No sub-sub-agents.
9. **Hard cap of 6 parallel agents** - No work-stealing or queue-based approach for larger task sets.

---

## 2. OSS Framework Survey

### 2.1 AutoGen (Microsoft)

**Pattern**: Conversation-based multi-agent with configurable agent topologies.
- Agents communicate through structured messages in a group chat
- `GroupChatManager` orchestrates turn-taking
- Supports "speaker selection" policies (round-robin, random, LLM-based)
- **Key insight**: Conversation-as-protocol -- agents can negotiate, disagree, and refine outputs through natural dialogue
- **Applicable to co-vibe**: The group chat pattern can be implemented as a `ConversationGroup` class where multiple agents share a message buffer

### 2.2 CrewAI

**Pattern**: Role-based agent teams with process-driven workflows.
- Each agent has a `role`, `goal`, and `backstory` (persona)
- Tasks are assigned with `expected_output` specifications
- Processes: `sequential` (waterfall), `hierarchical` (manager delegates)
- **Key insight**: Role specialization dramatically improves output quality -- a "reviewer" agent catches what a "coder" agent misses
- **Applicable to co-vibe**: Define agent roles (Researcher, Coder, Reviewer, Tester) with specialized system prompts and tool permissions

### 2.3 LangGraph

**Pattern**: Graph-based workflow with explicit state management.
- Agents are nodes in a directed graph; edges define control flow
- `StateGraph` with typed state that flows between nodes
- Supports conditional edges (routing based on agent output)
- Built-in checkpointing and human-in-the-loop interrupts
- **Key insight**: Explicit state graph makes complex workflows debuggable and reproducible
- **Applicable to co-vibe**: A lightweight DAG executor can handle sequential, parallel, and conditional task flows

### 2.4 OpenHands (formerly OpenDevin)

**Pattern**: Sandboxed coding agent with event-driven architecture.
- Event stream architecture: all actions and observations are events
- Docker-based sandbox for code execution
- Multi-agent via `AgentController` + `AgentDelegateAction`
- **Key insight**: Event sourcing makes agent actions fully auditable and replayable
- **Applicable to co-vibe**: An event log for all agent actions would enable replay, debugging, and learning

### 2.5 SWE-Agent

**Pattern**: Single-agent with environment interface, focused on software engineering.
- Custom "Agent-Computer Interface" (ACI) with specialized tools
- Search/navigate/edit workflow optimized for issue resolution
- Lightweight -- no multi-agent coordination, but very effective tool design
- **Key insight**: Tool quality matters more than agent quantity -- a well-designed tool interface beats a poorly orchestrated multi-agent system
- **Applicable to co-vibe**: co-vibe's tool set is already good; focus on orchestration quality over tool proliferation

### 2.6 Claude Code Team Feature

**Pattern**: TaskCreate/SendMessage/TeamCreate for hierarchical coordination.
- Team lead creates tasks with descriptions and dependencies
- Teammates claim tasks, work independently, report back via SendMessage
- Task system with `blocks`/`blockedBy` for dependency management
- Plan mode: agents draft plans for lead approval before executing
- **Key insight**: Asynchronous task-based coordination with explicit dependency tracking enables large-scale parallelism
- **Applicable to co-vibe**: co-vibe already has TaskCreate/Update but they are not used by sub-agents. Connecting the task system to the multi-agent coordinator would be a major upgrade.

### 2.7 MetaGPT

**Pattern**: SOP (Standard Operating Procedure) driven multi-agent.
- Agents follow predefined SOPs (e.g., ProductManager -> Architect -> Engineer -> QA)
- Shared `Environment` with message bus and document store
- Role-based output schemas (PRD, design doc, code, test plan)
- **Key insight**: Structured output requirements prevent agents from producing vague or redundant work
- **Applicable to co-vibe**: Output schemas for each agent role would improve result quality

---

## 3. Design Patterns for co-vibe

### 3.1 Agent Communication (Pattern A)

#### A1. Shared Blackboard (Recommended for single-file)

A thread-safe shared memory that all agents can read/write during parallel execution.

```python
class AgentBlackboard:
    """Thread-safe shared memory for multi-agent coordination."""

    def __init__(self):
        self._store = {}        # key -> value
        self._log = []          # ordered list of (agent_id, action, data)
        self._lock = threading.Lock()

    def write(self, agent_id, key, value):
        with self._lock:
            self._store[key] = value
            self._log.append((agent_id, "write", key, time.time()))

    def read(self, key, default=None):
        with self._lock:
            return self._store.get(key, default)

    def read_all(self):
        with self._lock:
            return dict(self._store)

    def append_finding(self, agent_id, finding):
        """Agents post intermediate findings for others to see."""
        with self._lock:
            findings = self._store.setdefault("_findings", [])
            findings.append({"agent": agent_id, "text": finding, "time": time.time()})

    def get_findings(self, since=0):
        with self._lock:
            findings = self._store.get("_findings", [])
            return [f for f in findings if f["time"] > since]
```

**Why**: Minimal overhead, thread-safe, no external dependencies. Each sub-agent periodically checks for new findings from other agents. Enables cross-agent knowledge sharing without requiring message passing infrastructure.

#### A2. Event Bus (For future extensibility)

```python
class AgentEventBus:
    """Publish-subscribe event bus for agent coordination."""

    def __init__(self):
        self._subscribers = {}  # event_type -> [callback]
        self._lock = threading.Lock()

    def subscribe(self, event_type, callback):
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def publish(self, event_type, data):
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))
        for cb in callbacks:
            try:
                cb(data)
            except Exception:
                pass
```

### 3.2 Orchestration Strategies (Pattern B)

#### B1. Hierarchical Orchestrator (Primary recommendation)

A lead agent plans and delegates to worker agents. This maps directly to the Claude Code team pattern.

```python
class HierarchicalOrchestrator:
    """Lead agent decomposes tasks and delegates to specialized workers."""

    ROLE_CONFIGS = {
        "researcher": {
            "system_prompt_suffix": (
                "You are a research specialist. Your job is to gather information, "
                "read code, search the web, and report findings clearly. "
                "Do NOT modify any files."
            ),
            "allowed_tools": {"Read", "Glob", "Grep", "WebFetch", "WebSearch"},
            "tier": "fast",       # research is usually IO-bound, fast model suffices
        },
        "coder": {
            "system_prompt_suffix": (
                "You are a coding specialist. Implement the changes described in your task. "
                "Write clean, tested code. Report what files you modified."
            ),
            "allowed_tools": {"Read", "Glob", "Grep", "Bash", "Write", "Edit"},
            "tier": "balanced",
        },
        "reviewer": {
            "system_prompt_suffix": (
                "You are a code review specialist. Review the code for bugs, "
                "security issues, style problems, and correctness. "
                "Be specific and actionable in your feedback."
            ),
            "allowed_tools": {"Read", "Glob", "Grep"},
            "tier": "strong",     # review benefits from strong reasoning
        },
        "tester": {
            "system_prompt_suffix": (
                "You are a testing specialist. Write and run tests for the described changes. "
                "Report test results clearly."
            ),
            "allowed_tools": {"Read", "Glob", "Grep", "Bash", "Write", "Edit"},
            "tier": "balanced",
        },
    }

    def __init__(self, config, client, registry, permissions):
        self._config = config
        self._client = client
        self._registry = registry
        self._permissions = permissions
        self._blackboard = AgentBlackboard()

    def plan_and_execute(self, user_request):
        """Use the strong model to decompose a task, then delegate to specialists."""
        # Phase 1: Planning (strong model)
        plan = self._create_plan(user_request)

        # Phase 2: Execute plan phases
        for phase in plan["phases"]:
            if phase["parallel"]:
                self._run_parallel_phase(phase["tasks"])
            else:
                for task in phase["tasks"]:
                    self._run_single_task(task)

        # Phase 3: Synthesize results
        return self._synthesize(user_request, self._blackboard.read_all())

    def _create_plan(self, user_request):
        """Ask strong model to decompose the request into a phased plan."""
        plan_prompt = (
            f"Decompose this request into a phased execution plan.\n"
            f"Available roles: {list(self.ROLE_CONFIGS.keys())}\n"
            f"Output JSON: {{\"phases\": [{{\"name\": str, \"parallel\": bool, "
            f"\"tasks\": [{{\"role\": str, \"prompt\": str}}]}}]}}\n\n"
            f"Request: {user_request}"
        )
        # Use strong model for planning
        resp = self._client.chat_sync(
            model=self._config.model_strong,
            messages=[
                {"role": "system", "content": "You are a task planner. Output only valid JSON."},
                {"role": "user", "content": plan_prompt},
            ],
        )
        return json.loads(resp.get("content", "{}"))
```

#### B2. DAG Workflow Engine

For complex multi-step workflows with dependencies:

```python
class DAGWorkflow:
    """Directed Acyclic Graph workflow executor.

    Nodes are agent tasks. Edges are dependencies.
    Tasks with no unmet dependencies run in parallel.
    """

    def __init__(self):
        self._nodes = {}       # node_id -> {"task": dict, "status": str, "result": str}
        self._edges = {}       # node_id -> [dependent_node_ids]
        self._reverse = {}     # node_id -> [dependency_node_ids]

    def add_node(self, node_id, task):
        self._nodes[node_id] = {"task": task, "status": "pending", "result": None}
        self._edges.setdefault(node_id, [])
        self._reverse.setdefault(node_id, [])

    def add_edge(self, from_id, to_id):
        """from_id must complete before to_id can start."""
        self._edges.setdefault(from_id, []).append(to_id)
        self._reverse.setdefault(to_id, []).append(from_id)

    def get_ready_nodes(self):
        """Return node IDs whose dependencies are all completed."""
        ready = []
        for nid, node in self._nodes.items():
            if node["status"] != "pending":
                continue
            deps = self._reverse.get(nid, [])
            if all(self._nodes[d]["status"] == "completed" for d in deps):
                ready.append(nid)
        return ready

    def execute(self, coordinator):
        """Execute the DAG, running ready nodes in parallel batches."""
        while True:
            ready = self.get_ready_nodes()
            if not ready:
                break
            tasks = [self._nodes[nid]["task"] for nid in ready]
            for nid in ready:
                self._nodes[nid]["status"] = "running"
            results = coordinator.run_parallel(tasks)
            for nid, result in zip(ready, results):
                self._nodes[nid]["status"] = "completed"
                self._nodes[nid]["result"] = result
        return {nid: n["result"] for nid, n in self._nodes.items()}
```

#### B3. Autonomous Swarm Mode

For large-scale exploratory tasks (e.g., codebase survey, documentation generation):

```python
class SwarmOrchestrator:
    """Autonomous agents that self-organize around a shared goal.

    Each agent:
    1. Reads the blackboard for current state
    2. Decides what to work on next
    3. Executes and posts results
    4. Repeats until the goal is met or budget is exhausted
    """

    def __init__(self, config, client, registry, permissions,
                 max_agents=6, max_rounds=5):
        self._config = config
        self._client = client
        self._registry = registry
        self._permissions = permissions
        self._blackboard = AgentBlackboard()
        self._max_agents = max_agents
        self._max_rounds = max_rounds

    def run(self, goal, initial_tasks=None):
        """Run the swarm until goal is met or budget exhausted."""
        self._blackboard.write("system", "goal", goal)
        if initial_tasks:
            self._blackboard.write("system", "task_queue", initial_tasks)

        for round_num in range(self._max_rounds):
            # Each agent reads blackboard, picks a task, executes, writes back
            task_queue = self._blackboard.read("task_queue", [])
            if not task_queue:
                break

            # Take up to max_agents tasks
            batch = task_queue[:self._max_agents]
            remaining = task_queue[self._max_agents:]
            self._blackboard.write("system", "task_queue", remaining)

            # Inject blackboard context into each agent's prompt
            context = self._blackboard.read_all()
            enhanced_tasks = []
            for task in batch:
                enhanced_prompt = (
                    f"## Shared Context\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
                    f"## Your Task\n{task['prompt']}\n\n"
                    f"Post your findings using the blackboard."
                )
                enhanced_tasks.append({**task, "prompt": enhanced_prompt})

            coordinator = MultiAgentCoordinator(
                self._config, self._client, self._registry, self._permissions
            )
            results = coordinator.run_parallel(enhanced_tasks)

            # Post-round: ask a synthesizer agent to update the blackboard
            self._synthesize_round(results, round_num)

        return self._blackboard.read_all()
```

### 3.3 Task Decomposition & Assignment (Pattern C)

#### C1. LLM-Powered Task Decomposition

Replace the current regex-based `_detect_parallel_tasks` with an LLM-powered decomposition step for complex requests:

```python
class SmartTaskDecomposer:
    """Use LLM to decompose complex requests into a structured task graph."""

    DECOMPOSE_SCHEMA = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "role": {"type": "string", "enum": ["researcher", "coder", "reviewer", "tester"]},
                        "prompt": {"type": "string"},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                        "estimated_complexity": {"type": "string", "enum": ["simple", "moderate", "complex"]},
                    },
                    "required": ["id", "role", "prompt"],
                },
            },
            "strategy": {
                "type": "string",
                "enum": ["sequential", "parallel", "dag"],
                "description": "Execution strategy based on task dependencies",
            },
        },
    }

    @staticmethod
    def should_decompose(user_input):
        """Quick heuristic: only invoke LLM decomposer for substantial requests."""
        if len(user_input) < 50:
            return False
        # Multiple action verbs, file references, or explicit multi-step indicators
        action_count = len(re.findall(
            r'(?:implement|create|fix|test|review|add|remove|update|refactor|'
            r'実装|作成|修正|テスト|レビュー|追加|削除|更新|リファクタ)',
            user_input, re.IGNORECASE
        ))
        return action_count >= 2

    def decompose(self, client, config, user_input):
        """Ask the strong model to decompose the request."""
        resp = client.chat_sync(
            model=config.model_strong or config.model,
            messages=[
                {"role": "system", "content": (
                    "You are a task decomposition engine. Given a user request, "
                    "break it into atomic tasks that can be assigned to specialist agents. "
                    "Output valid JSON matching the provided schema. "
                    "Minimize dependencies to maximize parallelism."
                )},
                {"role": "user", "content": user_input},
            ],
        )
        try:
            return json.loads(resp.get("content", "{}"))
        except json.JSONDecodeError:
            return None
```

#### C2. Dynamic Rebalancing

When one agent finishes early and others are still working:

```python
class DynamicRebalancer:
    """Monitor agent progress and redistribute work."""

    def __init__(self, blackboard):
        self._blackboard = blackboard

    def check_and_rebalance(self, active_agents, pending_tasks):
        """Check if any agent has finished and can take on more work.

        Called periodically by the coordinator during parallel execution.
        Returns list of (agent_id, new_task) assignments.
        """
        reassignments = []
        idle_agents = [a for a in active_agents if a["status"] == "completed"]

        if idle_agents and pending_tasks:
            for agent in idle_agents:
                if pending_tasks:
                    task = pending_tasks.pop(0)
                    reassignments.append((agent["id"], task))

        return reassignments
```

### 3.4 Self-Improvement (Pattern D)

#### D1. Execution History & Pattern Learning

```python
class ExecutionMemory:
    """Track execution patterns for self-improvement.

    Stores: task type -> {model_tier, tool_sequence, duration, success}
    After enough data, recommends optimal configurations.
    """

    MEMORY_FILE = ".co-vibe-memory.json"
    MAX_ENTRIES = 500

    def __init__(self, cwd):
        self._path = os.path.join(cwd, self.MEMORY_FILE)
        self._entries = self._load()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._entries[-self.MAX_ENTRIES:], f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def record(self, task_type, model_tier, tools_used, duration, success):
        self._entries.append({
            "type": task_type,
            "tier": model_tier,
            "tools": tools_used,
            "duration": duration,
            "success": success,
            "time": time.time(),
        })
        self._save()

    def recommend_tier(self, task_type):
        """Recommend model tier based on historical success rates."""
        relevant = [e for e in self._entries if e["type"] == task_type]
        if len(relevant) < 3:
            return None  # not enough data

        tier_stats = {}
        for entry in relevant[-20:]:  # last 20 entries
            tier = entry["tier"]
            if tier not in tier_stats:
                tier_stats[tier] = {"success": 0, "total": 0, "avg_duration": 0}
            tier_stats[tier]["total"] += 1
            if entry["success"]:
                tier_stats[tier]["success"] += 1
            tier_stats[tier]["avg_duration"] += entry["duration"]

        # Normalize
        for tier in tier_stats:
            stats = tier_stats[tier]
            stats["success_rate"] = stats["success"] / max(stats["total"], 1)
            stats["avg_duration"] /= max(stats["total"], 1)

        # Pick tier with best success rate, breaking ties by speed
        best = max(tier_stats.items(),
                   key=lambda x: (x[1]["success_rate"], -x[1]["avg_duration"]))
        return best[0]
```

#### D2. Adaptive Context Compression

Improve the current compaction to be context-aware:

```python
class AdaptiveCompactor:
    """Context-aware compaction that preserves task-relevant information.

    Instead of just summarizing old messages, it:
    1. Identifies the current task context
    2. Scores each message's relevance to the current task
    3. Preserves high-relevance messages even if old
    4. Aggressively compresses low-relevance messages
    """

    @staticmethod
    def score_relevance(message, current_task_keywords):
        """Score how relevant a message is to the current task (0-1)."""
        content = message.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        if not content:
            return 0.1  # tool calls still have some relevance

        content_lower = content.lower()
        score = 0.0
        for keyword in current_task_keywords:
            if keyword.lower() in content_lower:
                score += 0.2

        # File modifications are always relevant
        if message.get("role") == "tool" and any(
            w in content_lower for w in ["wrote", "edited", "created", "修正", "書き込み"]
        ):
            score += 0.3

        # Error messages are relevant
        if "error" in content_lower or "failed" in content_lower:
            score += 0.2

        return min(score, 1.0)
```

---

## 4. Concrete Implementation Proposal

### 4.1 Priority 1: Agent Roles & Blackboard (Low effort, High impact)

**Changes**:
1. Add `AgentBlackboard` class (~50 lines)
2. Add `ROLE_CONFIGS` dict to `SubAgentTool` with specialized system prompts
3. Modify `SubAgentTool.execute()` to accept a `role` parameter
4. Inject blackboard context into sub-agent system prompts
5. Modify `ParallelAgentTool` to create and pass a shared blackboard

**Estimated addition**: ~150 lines

```python
# In SubAgentTool, add role parameter:
"role": {
    "type": "string",
    "enum": ["researcher", "coder", "reviewer", "tester", "general"],
    "description": "Specialist role for this agent (affects system prompt and tools)",
},

# In SubAgentTool.execute(), use role to configure:
role_config = self.ROLE_CONFIGS.get(role, self.ROLE_CONFIGS["general"])
system_prompt = self._build_sub_system_prompt(self._config) + "\n" + role_config["system_prompt_suffix"]
allowed_tools = role_config["allowed_tools"]
```

### 4.2 Priority 2: LLM-Powered Task Decomposition (Medium effort, High impact)

**Changes**:
1. Add `SmartTaskDecomposer` class (~80 lines)
2. Replace regex-based `_detect_parallel_tasks` with a two-tier approach:
   - Keep regex for simple cases (fast, no API call)
   - Use LLM decomposer for complex requests (when `should_decompose()` returns True)
3. Add `DAGWorkflow` class (~60 lines) for dependency-aware execution

**Estimated addition**: ~200 lines

```python
# In Agent.run(), replace the auto-parallel detection:
if not self._plan_mode:
    # Tier 1: Fast regex detection (free)
    parallel_tasks = self._detect_parallel_tasks(user_input)
    if len(parallel_tasks) >= 2:
        # ... existing parallel dispatch ...

    # Tier 2: LLM decomposition for complex requests (costs 1 API call)
    elif SmartTaskDecomposer.should_decompose(user_input):
        decomposer = SmartTaskDecomposer()
        plan = decomposer.decompose(self.client, self.config, user_input)
        if plan and plan.get("tasks"):
            self._execute_plan(plan)
            return
```

### 4.3 Priority 3: Hierarchical Orchestrator Mode (Medium effort, High impact)

**Changes**:
1. Add `HierarchicalOrchestrator` class (~120 lines)
2. Add `--orchestrator` CLI flag (`flat` | `hierarchical` | `swarm`)
3. For `hierarchical` mode: strong model plans, then delegates to workers
4. Add result synthesis step that merges all agent outputs

**Estimated addition**: ~200 lines

### 4.4 Priority 4: Execution Memory (Low effort, Medium impact)

**Changes**:
1. Add `ExecutionMemory` class (~80 lines)
2. Record every agent execution (task type, tier, duration, success)
3. Use history to improve `_classify_complexity` heuristic
4. Store in `.co-vibe-memory.json` in project directory

**Estimated addition**: ~100 lines

### 4.5 Priority 5: Dynamic Work Queue (Medium effort, Medium impact)

**Changes**:
1. Replace thread-per-task with a work queue + worker pool
2. Enable work-stealing: when one agent finishes, it picks up pending work
3. Remove the hard cap of 6 agents; instead use a configurable pool size with default 6
4. Support for task queues larger than the pool size

**Estimated addition**: ~120 lines

```python
class WorkQueue:
    """Thread-pool with work-stealing for dynamic task execution."""

    def __init__(self, max_workers=6):
        self._queue = collections.deque()
        self._results = {}
        self._lock = threading.Lock()
        self._max_workers = max_workers

    def submit(self, task_id, task_fn):
        with self._lock:
            self._queue.append((task_id, task_fn))

    def run_all(self):
        """Run all queued tasks with a thread pool, enabling work-stealing."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {}

            def _worker(task_id, task_fn):
                result = task_fn()
                # After finishing, try to steal work from the queue
                while True:
                    with self._lock:
                        if not self._queue:
                            break
                        next_id, next_fn = self._queue.popleft()
                    next_result = next_fn()
                    self._results[next_id] = next_result
                return result

            # Submit initial batch
            with self._lock:
                initial_batch = []
                while self._queue and len(initial_batch) < self._max_workers:
                    initial_batch.append(self._queue.popleft())

            for task_id, task_fn in initial_batch:
                futures[task_id] = pool.submit(_worker, task_id, task_fn)

            for task_id, future in futures.items():
                self._results[task_id] = future.result(timeout=300)

        return self._results
```

### 4.6 Priority 6: Adaptive Context Compression (Low effort, Medium impact)

**Changes**:
1. Add relevance scoring to `Session.compact_if_needed()`
2. Preserve high-relevance messages even if old
3. Use current task context to determine keywords

**Estimated addition**: ~60 lines

---

## 5. Architecture Diagram

```
User Input
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Agent (main loop)                                │
│  ┌────────────────────────────────────────┐       │
│  │ SmartTaskDecomposer                    │       │
│  │  - Regex (fast, free)                  │       │
│  │  - LLM decompose (complex requests)    │       │
│  └───────────┬────────────────────────────┘       │
│              │                                     │
│              ▼                                     │
│  ┌────────────────────────────────────────┐       │
│  │ Orchestrator (configurable)            │       │
│  │  - flat (current behavior)             │       │
│  │  - hierarchical (plan → delegate)      │       │
│  │  - swarm (autonomous coordination)     │       │
│  └───────────┬────────────────────────────┘       │
│              │                                     │
│     ┌────────┴────────┐                            │
│     ▼                 ▼                            │
│  Sequential       DAGWorkflow                      │
│  execution        ┌───────────────────┐            │
│                   │ Phase 1 (parallel) │            │
│                   │ ┌─────┐ ┌─────┐   │            │
│                   │ │Rsrch│ │Rsrch│   │            │
│                   │ └──┬──┘ └──┬──┘   │            │
│                   │    └───┬───┘      │            │
│                   │ Phase 2 (depends) │            │
│                   │ ┌─────┐ ┌─────┐  │            │
│                   │ │Coder│ │Coder│  │            │
│                   │ └──┬──┘ └──┬──┘  │            │
│                   │    └───┬───┘     │            │
│                   │ Phase 3 (review) │            │
│                   │    ┌─────┐       │            │
│                   │    │Revwr│       │            │
│                   │    └─────┘       │            │
│                   └───────────────────┘            │
│                          │                         │
│                   ┌──────┴──────┐                  │
│                   │ Blackboard  │  (shared state)  │
│                   │ + WorkQueue │  (work-stealing) │
│                   └─────────────┘                  │
│                          │                         │
│                   ┌──────┴──────┐                  │
│                   │ Synthesizer │  (merge results) │
│                   └─────────────┘                  │
│                          │                         │
│                   ┌──────┴──────┐                  │
│                   │ Exec Memory │  (learn & adapt) │
│                   └─────────────┘                  │
└──────────────────────────────────────────────────┘
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Priorities 1+4) — ~250 lines added
- `AgentBlackboard` for shared memory
- `ROLE_CONFIGS` for agent specialization
- `ExecutionMemory` for learning
- **Impact**: Agents can share findings; specialized roles improve quality

### Phase 2: Smart Planning (Priority 2) — ~200 lines added
- `SmartTaskDecomposer` with two-tier detection
- `DAGWorkflow` for dependency-aware execution
- **Impact**: Complex requests auto-decompose into optimized execution plans

### Phase 3: Advanced Orchestration (Priorities 3+5) — ~320 lines added
- `HierarchicalOrchestrator` for plan-delegate-synthesize workflows
- `WorkQueue` with work-stealing for dynamic execution
- `--orchestrator` CLI flag
- **Impact**: Large-scale tasks (10+ sub-tasks) execute efficiently

### Phase 4: Polish (Priority 6) — ~60 lines added
- Adaptive context compression
- Execution history feedback into tier selection
- **Impact**: Longer sessions, better resource utilization

**Total estimated addition**: ~830 lines (bringing co-vibe.py to ~9,100 lines)

---

## 7. Key Design Decisions

### 7.1 Why Blackboard over Message Passing?
- **Single-file constraint**: Message passing requires queues, routing, and serialization. Blackboard is a simple dict with a lock.
- **Thread-safe by design**: Python's `threading.Lock` handles the concurrency.
- **Read-heavy workload**: Agents mostly read each other's findings. Blackboard's `read_all()` is O(1).
- **No agent discovery**: Agents don't need to know about each other -- they just read the shared state.

### 7.2 Why Two-Tier Decomposition?
- **Cost optimization**: Regex detection is free. Only complex requests (>50 chars, 2+ verbs) trigger an LLM call.
- **Backward compatibility**: Simple requests still use the fast regex path.
- **Quality**: LLM decomposition produces better task graphs than any regex can.

### 7.3 Why Not Full AutoGen/CrewAI/LangGraph?
- **Single-file constraint**: These frameworks are 10,000+ line multi-file projects with dependencies.
- **Dependency-free**: co-vibe uses only Python stdlib. Adding frameworks contradicts the design philosophy.
- **Cherry-picking**: We take the best ideas (roles from CrewAI, DAG from LangGraph, conversation from AutoGen) and implement them minimally.

### 7.4 Why Hierarchical as Default?
- **Proven in practice**: Claude Code's team system uses hierarchical coordination and it works well for coding tasks.
- **Clear accountability**: Each agent has a specific role and scope.
- **Debuggable**: The plan is visible; you can see what each agent was asked to do.
- **Swarm is optional**: For exploratory tasks, swarm mode is available via `--orchestrator swarm`.

---

## 8. Comparison with Current State

| Feature | Current co-vibe | Proposed co-vibe |
|---------|----------------|------------------|
| Max parallel agents | 6 (hard cap) | Configurable pool (default 6, work-stealing) |
| Task detection | Regex (numbered lists, bullets) | Regex + LLM decomposition |
| Agent specialization | None (generic prompt) | 4 roles (researcher, coder, reviewer, tester) |
| Inter-agent communication | None | Shared blackboard |
| Execution pattern | Flat parallel | DAG with phases (parallel + sequential) |
| Orchestration modes | 1 (flat) | 3 (flat, hierarchical, swarm) |
| Result handling | Concatenation | Intelligent synthesis |
| Learning | None | Execution memory with tier recommendation |
| Context compaction | Age-based trim | Relevance-scored adaptive compression |
| Task dependency | TaskCreate (isolated) | DAGWorkflow with blocks/blockedBy |

---

## 9. References

- AutoGen: https://github.com/microsoft/autogen
- CrewAI: https://github.com/joaomdmoura/crewAI
- LangGraph: https://github.com/langchain-ai/langgraph
- OpenHands: https://github.com/All-Hands-AI/OpenHands
- SWE-Agent: https://github.com/princeton-nlp/SWE-agent
- MetaGPT: https://github.com/geekan/MetaGPT
- Claude Code: https://docs.anthropic.com/en/docs/claude-code
