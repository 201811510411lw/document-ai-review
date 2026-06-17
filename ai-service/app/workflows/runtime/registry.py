from dataclasses import dataclass
from typing import Callable

from app.models import ReviewInputContext
from app.models.review import ReviewResult
from app.workflows.runtime.contract import ReviewGraphDefinition


@dataclass(frozen=True)
class ReviewRuntimeEntry:
    definition: ReviewGraphDefinition
    invoke: Callable[[ReviewInputContext], ReviewResult]


class ReviewGraphRegistry:
    def __init__(self) -> None:
        self._graphs: dict[str, ReviewGraphDefinition] = {}
        self._entries: dict[str, ReviewRuntimeEntry] = {}

    def register(self, graph: ReviewGraphDefinition) -> None:
        self._graphs[graph["name"]] = graph

    def register_entry(self, entry: ReviewRuntimeEntry) -> None:
        self._entries[entry.definition["name"]] = entry
        self.register(entry.definition)

    def get(self, graph_name: str) -> ReviewGraphDefinition:
        return self._graphs[graph_name]

    def get_entry(self, graph_name: str) -> ReviewRuntimeEntry:
        return self._entries[graph_name]

    def list(self) -> list[ReviewGraphDefinition]:
        return list(self._graphs.values())

    def select(self, input_context: ReviewInputContext) -> ReviewGraphDefinition:
        return self.select_entry(input_context).definition

    def select_entry(self, input_context: ReviewInputContext) -> ReviewRuntimeEntry:
        declared_document_type = input_context.input.declared_document_type
        candidates = [
            entry
            for entry in self._entries.values()
            if declared_document_type in entry.definition["supported_document_types"]
        ]
        if not candidates:
            graph_candidates = [
                graph
                for graph in self._graphs.values()
                if declared_document_type in graph["supported_document_types"]
            ]
            if len(graph_candidates) == 1:
                graph = graph_candidates[0]
                return ReviewRuntimeEntry(definition=graph, invoke=_missing_invoker)
            if len(graph_candidates) > 1:
                names = ", ".join(graph["name"] for graph in graph_candidates)
                raise ValueError(
                    "Multiple registered review graphs support the input context: "
                    f"{names}"
                )
            raise LookupError("No registered review graph supports the input context.")
        if len(candidates) == 1:
            return candidates[0]
        names = ", ".join(entry.definition["name"] for entry in candidates)
        raise ValueError(
            "Multiple registered review graphs support the input context: "
            f"{names}"
        )


def _missing_invoker(input_context: ReviewInputContext) -> ReviewResult:
    raise RuntimeError("Selected review graph does not have an invoker registered.")
