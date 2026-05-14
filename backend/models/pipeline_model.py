"""
Pipeline model - saved transformation workflows.
"""
from typing import Dict, List
from typing import Optional
from dataclasses import dataclass, field
import uuid

import json
import time
from utils.db import db
from utils.logger import logger

@dataclass
class PipelineStep:
    action: str
    params: Dict = field(default_factory=dict)

@dataclass
class Pipeline:
    name: str
    steps: List[PipelineStep]
    owner_id: str = ""
    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4()))

def save_pipeline(p: Pipeline) -> None:
    try:
        steps_json = json.dumps([{"action": s.action, "params": s.params} for s in p.steps])
        db.execute(
            """INSERT INTO pipelines (id, owner_id, name, steps, created_at)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE name=%s, steps=%s""",
            (p.pipeline_id, p.owner_id, p.name, steps_json, time.time(), p.name, steps_json)
        )
    except Exception as e:
        logger.error(f"Failed to save pipeline: {e}")
        raise

def get_pipeline(pid: str, owner_id: str = "") -> Optional[Pipeline]:
    if owner_id:
        row = db.fetchone(
            "SELECT * FROM pipelines WHERE id = %s AND owner_id = %s",
            (pid, owner_id),
        )
    else:
        row = db.fetchone("SELECT * FROM pipelines WHERE id = %s", (pid,))
    if not row: return None
    steps_data = json.loads(row["steps"])
    steps = [PipelineStep(action=s["action"], params=s.get("params", {})) for s in steps_data]
    return Pipeline(name=row["name"], steps=steps, pipeline_id=row["id"], owner_id=row["owner_id"])

def list_pipelines(owner_id: str = "") -> List[Pipeline]:
    if owner_id:
        rows = db.fetchall("SELECT * FROM pipelines WHERE owner_id = %s", (owner_id,))
    else:
        rows = db.fetchall("SELECT * FROM pipelines", ())
    pipelines = []
    for row in rows:
        steps_data = json.loads(row["steps"])
        steps = [PipelineStep(action=s["action"], params=s.get("params", {})) for s in steps_data]
        pipelines.append(Pipeline(name=row["name"], steps=steps, pipeline_id=row["id"], owner_id=row["owner_id"]))
    return pipelines
