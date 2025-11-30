"""
AgentOrchestrator DAG Visualization

Generates ASCII and Mermaid visualizations of chain DAGs.
"""

from dataclasses import dataclass

from agentorchestrator.core.registry import get_chain_registry, get_step_registry


@dataclass
class NodeStyle:
    """Styling for DAG nodes"""

    width: int = 30
    connector: str = "──"
    arrow: str = "▶"


class DAGVisualizer:
    """
    Generates ASCII and Mermaid visualizations of AgentOrchestrator chains.

    Usage:
        viz = DAGVisualizer()
        print(viz.to_ascii("meeting_prep_chain"))
        print(viz.to_mermaid("meeting_prep_chain"))

        # With custom registries (for isolated forge instances)
        viz = DAGVisualizer(
            step_registry=forge._step_registry,
            chain_registry=forge._chain_registry
        )
    """

    def __init__(
        self,
        style: NodeStyle | None = None,
        step_registry=None,
        chain_registry=None,
    ):
        self.style = style or NodeStyle()
        self.step_registry = step_registry or get_step_registry()
        self.chain_registry = chain_registry or get_chain_registry()

    def to_ascii(self, chain_name: str) -> str:
        """Generate ASCII visualization of a chain DAG"""
        chain_spec = self.chain_registry.get_spec(chain_name)
        if not chain_spec:
            return f"Chain not found: {chain_name}"

        lines = []
        lines.append(self._box(f"Chain: {chain_name}", width=60))
        lines.append("")

        # Use explicit parallel groups if defined, otherwise compute from deps
        if chain_spec.parallel_groups:
            levels = chain_spec.parallel_groups
            lines.append(self._center("(using explicit parallel_groups)", 60))
            lines.append("")
        else:
            levels = self._compute_levels(chain_spec.steps)

        for level_idx, level_steps in enumerate(levels):
            is_parallel = len(level_steps) > 1

            if is_parallel:
                lines.append(self._center("┌" + "─" * 25 + " PARALLEL " + "─" * 24 + "┐", 60))

            for step_idx, step_name in enumerate(level_steps):
                step_spec = self.step_registry.get_spec(step_name)
                deps = step_spec.dependencies if step_spec else []

                step_box = self._step_box(
                    step_name, deps, produces=step_spec.produces if step_spec else []
                )
                lines.append(step_box)

                if step_idx < len(level_steps) - 1 and is_parallel:
                    lines.append(self._center("│" + " " * 58 + "│", 60))

            if is_parallel:
                lines.append(self._center("└" + "─" * 58 + "┘", 60))

            if level_idx < len(levels) - 1:
                lines.append(self._center("│", 60))
                lines.append(self._center("▼", 60))
                lines.append("")

        return "\n".join(lines)

    def to_mermaid(self, chain_name: str) -> str:
        """Generate Mermaid.js diagram syntax"""
        chain_spec = self.chain_registry.get_spec(chain_name)
        if not chain_spec:
            return f"Chain not found: {chain_name}"

        lines = ["graph TD"]

        # Add nodes
        for step_name in chain_spec.steps:
            label = step_name.replace("_", " ").title()
            lines.append(f"    {step_name}[{label}]")

        lines.append("")

        # Add edges based on dependencies
        for step_name in chain_spec.steps:
            step_spec = self.step_registry.get_spec(step_name)
            if step_spec and step_spec.dependencies:
                for dep in step_spec.dependencies:
                    lines.append(f"    {dep} --> {step_name}")

        # Add subgraphs for explicit parallel groups
        if chain_spec.parallel_groups:
            lines.append("")
            lines.append("    %% Explicit parallel groups")
            for idx, group in enumerate(chain_spec.parallel_groups):
                if len(group) > 1:
                    lines.append(f"    subgraph parallel_group_{idx}[Parallel Group {idx + 1}]")
                    for step in group:
                        lines.append(f"        {step}")
                    lines.append("    end")

        return "\n".join(lines)

    def _compute_levels(self, steps: list[str]) -> list[list[str]]:
        """Group steps into execution levels based on dependencies"""
        levels = []
        placed = set()

        while len(placed) < len(steps):
            level = []
            for step_name in steps:
                if step_name in placed:
                    continue

                step_spec = self.step_registry.get_spec(step_name)
                deps = set(step_spec.dependencies) if step_spec else set()

                if deps.issubset(placed):
                    level.append(step_name)

            if not level:
                # Remaining steps (might have missing dependencies)
                level = [s for s in steps if s not in placed]

            levels.append(level)
            placed.update(level)

        return levels

    def _box(self, text: str, width: int = 40) -> str:
        """Create a box around text"""
        padding = max(0, width - len(text) - 4)
        left_pad = padding // 2
        right_pad = padding - left_pad
        top = "┌" + "─" * (width - 2) + "┐"
        middle = "│ " + " " * left_pad + text + " " * right_pad + " │"
        bottom = "└" + "─" * (width - 2) + "┘"
        return f"{top}\n{middle}\n{bottom}"

    def _step_box(self, name: str, deps: list[str], produces: list[str]) -> str:
        """Create a step representation"""
        lines = []
        lines.append(self._center(f"┌{'─' * 40}┐", 60))
        lines.append(self._center(f"│ {name:<38} │", 60))
        if deps:
            dep_str = f"deps: {', '.join(deps)}"[:37]
            lines.append(self._center(f"│ {dep_str:<38} │", 60))
        if produces:
            prod_str = f"→ {', '.join(produces)}"[:37]
            lines.append(self._center(f"│ {prod_str:<38} │", 60))
        lines.append(self._center(f"└{'─' * 40}┘", 60))
        return "\n".join(lines)

    def _center(self, text: str, width: int) -> str:
        """Center text within width"""
        padding = max(0, width - len(text))
        left = padding // 2
        return " " * left + text
