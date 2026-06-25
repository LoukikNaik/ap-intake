"""Run context passed to tools (dependency injection).

The LLM never sees this object directly — tools read it. We preload the editable GL
accounts here so the GL-mapping tool returns the manager's current, live list.
"""

from dataclasses import dataclass, field


@dataclass
class GLAccountView:
    code: str
    name: str
    description: str


@dataclass
class PipelineContext:
    gl_accounts: list[GLAccountView] = field(default_factory=list)
