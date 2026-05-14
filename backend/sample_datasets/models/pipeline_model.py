"""
Pipeline model - saved transformation workflows.
"""
from typing import Dict, List
from typing import Optional
from dataclasses import dataclass, field
import uuid

@dataclass
class PipelineStep:
    action: str
    params: Dict = field(default_factory=dict)

@dataclass
class Pipeline:
    name: str
    steps: List[PipelineStep]
    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4()))

# In-memory pipeline store
_pipelines: Dict[str, Pipeline] = {}

def save_pipeline(p: Pipeline) -> None:
    _pipelines[p.pipeline_id] = p

def get_pipeline(pid: str) -> Optional[Pipeline]:
    return _pipelines.get(pid)

def list_pipelines() -> List[Pipeline]:
    return list(_pipelines.values())
