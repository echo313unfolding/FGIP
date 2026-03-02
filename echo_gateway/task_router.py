"""Task Router - Unified routing to Basin/Cell/Swarm backends.

Routes incoming tasks to the appropriate backend:
- chat: Basin (LLM) for conversational queries
- cell: Single FGIPAgent for focused evidence gathering
- swarm: Multiple agents via ThreadPoolExecutor for parallel collection
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import importlib
import json

from .llm_client import LLMClient
from .receipt import Receipt, generate_receipt
from .kat_gate import KATGate, KATMode, KATGateResult


class TaskType(Enum):
    """Task types supported by the router."""

    CHAT = "chat"
    CELL = "cell"
    SWARM = "swarm"


@dataclass
class TaskResult:
    """Result of a routed task."""

    success: bool
    result: Any
    receipt: Receipt
    kat_gate: Optional[KATGateResult] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "result": self.result,
            "receipt": self.receipt.to_dict(),
            "kat_gate": self.kat_gate.to_dict() if self.kat_gate else None,
            "errors": self.errors if self.errors else None,
        }


# Agent registry (subset of schedule_runner.py for dynamic loading)
AGENT_REGISTRY = {
    # Tier 0 - Government primary sources
    "edgar": {"module": "fgip.agents.edgar", "class": "EDGARAgent"},
    "usaspending": {"module": "fgip.agents.usaspending", "class": "USASpendingAgent"},
    "gao": {"module": "fgip.agents.gao", "class": "GAOAgent"},
    "federal-register": {"module": "fgip.agents.federal_register", "class": "FederalRegisterAgent"},
    "tic": {"module": "fgip.agents.tic", "class": "TICAgent"},
    "scotus": {"module": "fgip.agents.scotus", "class": "SCOTUSAgent"},
    "fara": {"module": "fgip.agents.fara", "class": "FARAAgent"},
    "fec": {"module": "fgip.agents.fec", "class": "FECAgent"},
    "congress": {"module": "fgip.agents.congress", "class": "CongressAgent"},
    # Tier 1 - Journalism
    "rss": {"module": "fgip.agents.rss_signal", "class": "RSSSignalAgent"},
    "opensecrets": {"module": "fgip.agents.opensecrets", "class": "OpenSecretsAgent"},
    "promethean": {"module": "fgip.agents.promethean", "class": "PrometheanAgent"},
    # Tier 4 - Conviction
    "conviction-engine": {"module": "fgip.agents.conviction_engine", "class": "ConvictionEngine"},
    # Tier 5 - Calibration
    "forecast-agent": {"module": "fgip.agents.forecast_agent", "class": "ForecastAgent"},
}


def load_agent(name: str, db):
    """Dynamically load an agent by name."""
    # Normalize name
    normalized = name.lower().replace("_", "-")

    if normalized not in AGENT_REGISTRY:
        raise ValueError(f"Unknown agent: {name}. Available: {list(AGENT_REGISTRY.keys())}")

    info = AGENT_REGISTRY[normalized]
    module = importlib.import_module(info["module"])
    agent_class = getattr(module, info["class"])
    return agent_class(db)


class TaskRouter:
    """
    Unified task router for Echo Gateway.

    Routes tasks to appropriate backend:
    - chat: Basin (LLM) for conversational queries
    - cell: Single FGIPAgent for focused evidence gathering
    - swarm: Multiple agents via ThreadPoolExecutor
    """

    def __init__(
        self,
        db,
        llm_client: LLMClient,
        max_swarm_workers: int = 4,
        kat_mode: KATMode = KATMode.TRUST_CACHED,
        kat_sample_rate: float = 0.1,
        kat_cache_minutes: int = 15,
    ):
        """
        Initialize task router.

        Args:
            db: FGIPDatabase instance
            llm_client: LLMClient for chat tasks
            max_swarm_workers: Max workers for swarm tasks
            kat_mode: KAT verification mode
            kat_sample_rate: Sampling rate for VERIFY_SAMPLED mode
            kat_cache_minutes: Cache duration for TRUST_CACHED mode
        """
        self.db = db
        self.llm_client = llm_client
        self.max_swarm_workers = max_swarm_workers
        self.kat_gate = KATGate(
            db=db,
            mode=kat_mode,
            sample_rate=kat_sample_rate,
            cache_minutes=kat_cache_minutes,
        )
        self._executor: Optional[ThreadPoolExecutor] = None

    def _get_executor(self) -> ThreadPoolExecutor:
        """Get or create thread pool executor."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_swarm_workers)
        return self._executor

    def shutdown(self):
        """Shutdown thread pool executor."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    async def route(
        self,
        task_type: str,
        payload: dict,
        require_kat: bool = False,
    ) -> TaskResult:
        """
        Route task to appropriate backend.

        Args:
            task_type: 'chat', 'cell', or 'swarm'
            payload: Task-specific payload
            require_kat: Force KAT verification

        Returns:
            TaskResult with result, receipt, and optional KAT gate info
        """
        start_time = time.time()

        try:
            task_enum = TaskType(task_type.lower())
        except ValueError:
            return TaskResult(
                success=False,
                result=None,
                receipt=generate_receipt(
                    task_type=task_type,
                    backend_used="error",
                    start_time=start_time,
                    inputs=payload,
                    outputs=None,
                ),
                errors=[f"Invalid task_type: {task_type}. Must be 'chat', 'cell', or 'swarm'."],
            )

        if task_enum == TaskType.CHAT:
            return await self._route_chat(payload, start_time, require_kat)
        elif task_enum == TaskType.CELL:
            return await self._route_cell(payload, start_time, require_kat)
        elif task_enum == TaskType.SWARM:
            return await self._route_swarm(payload, start_time, require_kat)

    async def _route_chat(
        self,
        payload: dict,
        start_time: float,
        require_kat: bool,
    ) -> TaskResult:
        """Route to Basin (LLM) for chat tasks."""
        messages = payload.get("messages", [])
        tools = payload.get("tools")
        temperature = payload.get("temperature", 0.0)

        try:
            response = await self.llm_client.chat(
                messages=messages,
                tools=tools,
                temperature=temperature,
            )

            # Extract content from response
            choices = response.get("choices", [])
            if choices:
                result = choices[0].get("message", {})
            else:
                result = {"error": "No response from LLM"}

            # Detect backend from URL (cdna vs ollama)
            backend_name = "cdna" if "7778" in self.llm_client.base_url else "ollama"
            router_path = f"chat->llmclient->{backend_name}"

            return TaskResult(
                success=True,
                result=result,
                receipt=generate_receipt(
                    task_type="chat",
                    backend_used="basin",
                    start_time=start_time,
                    inputs=payload,
                    outputs=result,
                    llm_base_url=self.llm_client.base_url,
                    llm_model=self.llm_client.model,
                    router_path=router_path,
                ),
            )
        except Exception as e:
            backend_name = "cdna" if "7778" in self.llm_client.base_url else "ollama"
            router_path = f"chat->llmclient->{backend_name}"

            return TaskResult(
                success=False,
                result=None,
                receipt=generate_receipt(
                    task_type="chat",
                    backend_used="basin",
                    start_time=start_time,
                    inputs=payload,
                    outputs=None,
                    llm_base_url=self.llm_client.base_url,
                    llm_model=self.llm_client.model,
                    router_path=router_path,
                ),
                errors=[str(e)],
            )

    async def _route_cell(
        self,
        payload: dict,
        start_time: float,
        require_kat: bool,
    ) -> TaskResult:
        """Route to single FGIPAgent for cell tasks."""
        agent_name = payload.get("agent")
        if not agent_name:
            return TaskResult(
                success=False,
                result=None,
                receipt=generate_receipt(
                    task_type="cell",
                    backend_used="cell",
                    start_time=start_time,
                    inputs=payload,
                    outputs=None,
                ),
                errors=["Missing 'agent' in payload"],
            )

        try:
            # Load and run agent
            agent = load_agent(agent_name, self.db)
            result = agent.run_with_delta()

            # Check KAT gate for phenotype agents
            kat_result = None
            if self.kat_gate.requires_verification(agent_name, force=require_kat):
                allowed, gated_result, kat_result = self.kat_gate.gate_output(
                    agent_name=agent_name,
                    output=result,
                    require_kat=require_kat,
                )
                if not allowed:
                    return TaskResult(
                        success=False,
                        result=gated_result,
                        receipt=generate_receipt(
                            task_type="cell",
                            backend_used="cell",
                            start_time=start_time,
                            inputs=payload,
                            outputs=gated_result,
                        ),
                        kat_gate=kat_result,
                        errors=["Phenotype expression blocked by KAT gate"],
                    )

            return TaskResult(
                success=True,
                result=result,
                receipt=generate_receipt(
                    task_type="cell",
                    backend_used="cell",
                    start_time=start_time,
                    inputs=payload,
                    outputs=result,
                ),
                kat_gate=kat_result,
            )
        except Exception as e:
            return TaskResult(
                success=False,
                result=None,
                receipt=generate_receipt(
                    task_type="cell",
                    backend_used="cell",
                    start_time=start_time,
                    inputs=payload,
                    outputs=None,
                ),
                errors=[str(e)],
            )

    async def _route_swarm(
        self,
        payload: dict,
        start_time: float,
        require_kat: bool,
    ) -> TaskResult:
        """Route to multiple agents via ThreadPoolExecutor for swarm tasks."""
        agents = payload.get("agents", [])
        if not agents:
            return TaskResult(
                success=False,
                result=None,
                receipt=generate_receipt(
                    task_type="swarm",
                    backend_used="swarm",
                    start_time=start_time,
                    inputs=payload,
                    outputs=None,
                ),
                errors=["Missing 'agents' list in payload"],
            )

        executor = self._get_executor()
        results = {}
        errors = []

        def run_agent_sync(agent_name: str) -> Tuple[str, Any, Optional[str]]:
            """Run single agent synchronously (for thread pool)."""
            try:
                agent = load_agent(agent_name, self.db)
                result = agent.run_with_delta()
                return (agent_name, result, None)
            except Exception as e:
                return (agent_name, None, str(e))

        # Submit all agents to thread pool
        futures = {
            executor.submit(run_agent_sync, agent_name): agent_name
            for agent_name in agents
        }

        # Collect results
        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                name, result, error = future.result()
                if error:
                    errors.append(f"{name}: {error}")
                    results[name] = {"error": error}
                else:
                    results[name] = result
            except Exception as e:
                errors.append(f"{agent_name}: {str(e)}")
                results[agent_name] = {"error": str(e)}

        # KAT gate check if any phenotype agent in swarm
        kat_result = None
        phenotype_agents = [a for a in agents if self.kat_gate.requires_verification(a)]
        if phenotype_agents or require_kat:
            kat_result = self.kat_gate.verify(force=require_kat)
            if not kat_result.passed:
                # Block phenotype outputs, keep non-phenotype results
                for agent_name in phenotype_agents:
                    results[agent_name] = {
                        "error": "phenotype_blocked",
                        "reason": "KAT verification failed",
                    }

        success = len(errors) == 0 or (kat_result and not kat_result.passed and len(errors) == len(phenotype_agents))

        return TaskResult(
            success=success,
            result=results,
            receipt=generate_receipt(
                task_type="swarm",
                backend_used="swarm",
                start_time=start_time,
                inputs=payload,
                outputs=results,
                metadata={"agent_count": len(agents)},
            ),
            kat_gate=kat_result,
            errors=errors if errors else None,
        )
