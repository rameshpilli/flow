"""PRE expert implementation."""

from __future__ import annotations

from pathlib import Path

from examples.polecat_swarm.agents.base_expert import BaseExpert
from examples.polecat_swarm.types import ExpertResult


class ProductRequirementsExpert(BaseExpert):
    role = "PRE"

    def run(self) -> ExpertResult:
        title = str(self.bead.get("title") or "")
        description = str(self.bead.get("description") or "")

        if not description.strip():
            return ExpertResult(
                status="blocked",
                notes="Bead has no description. Provide product requirements context.",
            )

        prd_files = self._discover_prd_files()
        criteria = [
            f"Given bead {self.bead_id}, when implementation completes, then feature behavior matches task intent.",
            "Given tests are executed, then all configured checks pass.",
            "Given docs are enabled, then docs are updated with behavior changes.",
        ]
        dod = [
            "Code changes committed in worktree",
            "QA checks executed",
            "Documentation updated when applicable",
            "Release artifact summary produced",
        ]

        requirements_md = "\n".join(
            [
                f"# Requirements for {self.bead_id}",
                "",
                f"## Title\n{title}",
                "",
                f"## Description\n{description}",
                "",
                "## PRD Files",
                *((f"- {path}" for path in prd_files) if prd_files else ["- none found"]),
                "",
                "## Acceptance Criteria",
                *(f"- {item}" for item in criteria),
                "",
                "## Definition of Done",
                *(f"- {item}" for item in dod),
            ]
        )
        artifact = self.write_artifact("requirements.md", requirements_md)

        return ExpertResult(
            status="success",
            notes="Requirements artifact generated",
            artifacts=[artifact],
            metadata={"acceptance_criteria": criteria, "definition_of_done": dod},
        )

    def _discover_prd_files(self) -> list[str]:
        repo = Path(self.worktree)
        candidates = [
            *repo.glob("docs/PRD*.md"),
            *repo.glob("docs/RFC*.md"),
            *repo.glob("PRODUCT.md"),
        ]
        output: list[str] = []
        for path in candidates:
            if path.is_file():
                try:
                    output.append(str(path.relative_to(repo)))
                except Exception:
                    output.append(str(path))
        return sorted(set(output))
