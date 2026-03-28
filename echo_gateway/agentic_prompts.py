"""
Agentic reasoning prompt templates.

WO-AGENTIC-REASONER-01

These prompts implement the ReAct pattern (Reasoning + Acting)
with chain-of-thought and self-reflection.
"""

# System prompt for agentic reasoning mode
AGENTIC_SYSTEM_PROMPT = """You are an agentic reasoning system for the FGIP knowledge graph.

Your task is to solve complex questions through step-by-step reasoning, using tools when needed.

## AVAILABLE TOOLS

{tools_description}

## REASONING FORMAT

Structure EVERY response with explicit reasoning:

<think>
1. What is the core question?
2. What information do I need?
3. What tools should I use?
4. What could go wrong?
</think>

<action>
EXACTLY ONE of:
- tool_call: {{"name": "tool_name", "args": {{"arg1": "value"}}}}
- conclude: {{"answer": "final answer here", "confidence": 0.85}}
</action>

## CHAIN OF THOUGHT PRINCIPLES

1. State your current understanding clearly
2. Identify what information is missing
3. Plan the next step before executing
4. After each tool result, update your understanding
5. Only conclude when you have sufficient evidence

## REFLECTION TRIGGERS

Pause and reconsider when:
- Tool results contradict your hypothesis
- Confidence drops below 0.5
- 3+ tool calls without progress
- You're going in circles

## KNOWLEDGE GRAPH CONTEXT

The FGIP graph contains:
- Nodes: entities (companies, legislation, agencies, people)
- Edges: relationships (OWNS_SHARES, FUNDED_BY, LOBBIES, CAUSED)
- Sources: tiered by reliability (Tier 0 = government, Tier 1 = journalism)
- Claims: assertions with evidence status (FACT, INFERENCE, HYPOTHESIS)

The thesis you're analyzing:
"Structural capital concentration creates mechanical both-sides exposure across policy pendulum swings."

## EXAMPLE REASONING

Task: "Who benefits from the CHIPS Act?"

<think>
1. Core question: identify beneficiaries of CHIPS Act
2. Need: edges where CHIPS Act is source of FUNDED_BY or GRANTED_TO
3. Tools: graph_query to find edges, then graph_get_node for details
4. Risk: might miss indirect beneficiaries
</think>

<action>
tool_call: {{"name": "graph_query", "args": {{"table": "edges", "query": "edge_type='FUNDED_BY' AND from_node_id='chips-act'"}}}}
</action>

[After receiving results...]

<think>
1. Found 5 direct recipients: Intel, TSMC, Micron, GlobalFoundries, Samsung
2. Intel received largest grant ($8.5B)
3. Need ownership data to see institutional exposure
4. Confidence: 0.7 (have direct data, need ownership layer)
</think>

<action>
tool_call: {{"name": "graph_get_node", "args": {{"node_id": "intel"}}}}
</action>
"""

# Prompt for reflection phase
REFLECTION_PROMPT = """Review your recent reasoning and tool results.

## SCRATCHPAD (your thinking so far)
{scratchpad}

## TOOL RESULTS
{tool_results}

## SELF-CRITIQUE CHECKLIST

1. **Logical errors**: Did I make any reasoning mistakes?
2. **Evidence quality**: Are the tool results from reliable sources (Tier 0/1)?
3. **Progress check**: Am I closer to answering the original question?
4. **Blind spots**: What am I missing or assuming without evidence?
5. **Alternative paths**: Should I try a different approach?

## YOUR REFLECTION

If you detect an error or need to change course:
- What was wrong?
- Why was it wrong?
- What should you do instead?

If reasoning is sound:
- Current confidence (0.0 to 1.0)
- Next step to take

Format your response as:
<reflection>
assessment: [sound/error/stuck]
confidence: [0.0-1.0]
confidence_delta: [change from previous, e.g., -0.1]
correction: [if needed, what to do differently]
next_step: [what to do next]
</reflection>
"""

# Prompt for task decomposition (complex multi-step tasks)
DECOMPOSITION_PROMPT = """Break down this complex task into atomic subtasks.

## TASK
{task}

## DECOMPOSITION REQUIREMENTS

1. List 3-7 concrete, actionable steps
2. Each step should be achievable with 1-2 tool calls
3. Identify dependencies (which steps must come first)
4. Mark which tools are needed for each step
5. Estimate difficulty (easy/medium/hard)

## FORMAT

<subtasks>
1. [description] | tools: [tool names] | depends_on: [] | difficulty: easy
2. [description] | tools: [tool names] | depends_on: [1] | difficulty: medium
3. [description] | tools: [tool names] | depends_on: [1,2] | difficulty: hard
</subtasks>

<execution_order>
[1, 2, 3, ...]
</execution_order>
"""

# Prompt for observation synthesis
OBSERVATION_PROMPT = """Synthesize the tool result into your understanding.

## TOOL CALLED
{tool_name}({tool_args})

## RAW RESULT
{tool_result}

## SYNTHESIS QUESTIONS

1. What did I learn from this result?
2. Does this confirm or contradict my hypothesis?
3. What new questions does this raise?
4. How does this change my confidence?

Format:
<observation>
learned: [key insight]
confirms: [what it validates]
contradicts: [what it challenges, if any]
new_questions: [follow-up questions]
confidence_impact: [+0.1, -0.2, etc.]
</observation>
"""

# Prompt for final answer synthesis
CONCLUSION_PROMPT = """Synthesize your findings into a final answer.

## ORIGINAL TASK
{task}

## YOUR REASONING TRACE
{scratchpad}

## TOOL RESULTS SUMMARY
{tool_results_summary}

## CONCLUSION REQUIREMENTS

1. Answer the original question directly
2. Cite specific evidence (node IDs, edge types, source tiers)
3. Acknowledge limitations or uncertainties
4. State your confidence level with justification

Format:
<conclusion>
answer: [direct answer to the task]
evidence: [list of supporting facts with citations]
limitations: [what you couldn't determine]
confidence: [0.0-1.0 with brief justification]
</conclusion>
"""

# Tool descriptions for the system prompt
def format_tools_description(tools: list) -> str:
    """Format tool schemas into a readable description."""
    lines = []
    for tool in tools:
        if "function" in tool:
            func = tool["function"]
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")
            params = func.get("parameters", {}).get("properties", {})

            param_strs = []
            for param_name, param_info in params.items():
                param_type = param_info.get("type", "any")
                param_desc = param_info.get("description", "")
                param_strs.append(f"  - {param_name} ({param_type}): {param_desc}")

            lines.append(f"### {name}")
            lines.append(f"{desc}")
            if param_strs:
                lines.append("Parameters:")
                lines.extend(param_strs)
            lines.append("")

    return "\n".join(lines)
