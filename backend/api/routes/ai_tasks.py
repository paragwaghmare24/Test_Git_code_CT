"""Approval-controlled AI tasks. Blocking SDK calls run in FastAPI's thread pool."""
from typing import Literal
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from backend.services import ai_tasks as tasks
from backend.utils.ai_gate import AINotApprovedError

router = APIRouter(prefix="/api/ai/tasks", tags=["ai-tasks"])


def _call(fn, *args):
    try:
        return fn(*args)
    except AINotApprovedError as exc:
        raise HTTPException(403, str(exc))
    except FileNotFoundError:
        raise HTTPException(404, "AI task or approval not found")
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, str(exc))


@router.post("")
def create_task(request_id: str = Form(...), panel: str = Form(...),
                instruction: str = Form(...), context: str = Form(""),
                data_policy: str = Form("undecided"), files: list[UploadFile] = File(default=[])):
    sources = []
    for file in files:
        content = file.file.read(tasks.MAX_BYTES + 1)
        if len(content) > tasks.MAX_BYTES:
            raise HTTPException(413, "Source exceeds 10 MB; split the input.")
        sources.append((file.filename or "source.txt", content))
    return _call(tasks.create, request_id, panel, instruction, context, sources, data_policy)


class Decision(BaseModel):
    revision: int
    action: Literal["adopt", "reject", "execute", "retrieve", "continue", "reply"]
    request_id: str = ""
    message: str = ""
    data_policy: Literal["undecided", "supplied", "duplicate", "synthetic"] = "undecided"


@router.post("/{task_id}/actions")
def act(task_id: str, decision: Decision):
    return _call(tasks.act, task_id, decision.revision, decision.action, decision.request_id,
                 decision.message, decision.data_policy)


@router.get("/{task_id}")
def get_task(task_id: str):
    return tasks.public(_call(tasks.load, task_id))


@router.get("/{task_id}/artifacts/{artifact_id}")
def download(task_id: str, artifact_id: str):
    task = _call(tasks.load, task_id)
    artifact = next((a for a in task["artifacts"] if a["id"] == artifact_id), None)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    return FileResponse(tasks._path(task_id) / artifact["id"], filename=artifact["name"],
                        media_type="application/octet-stream")