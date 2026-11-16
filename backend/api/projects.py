from __future__ import annotations

from fastapi import APIRouter, Response

from backend.api.deps import SessionDep, StorageDep, load_project
from backend.models.schemas import AssetOut, JobOut, ProjectCreate, ProjectOut, ProjectUpdate
from backend.models.tables import Job, Project
from backend.services import assets as asset_service
from backend.services import projects as project_service
from sqlalchemy import select

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(session: SessionDep):
    return project_service.list_projects(session)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, session: SessionDep):
    project = Project(name=body.name.strip(), description=body.description.strip())
    session.add(project)
    session.commit()
    return project_service.to_out(session, project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, session: SessionDep):
    return project_service.to_out(session, load_project(session, project_id))


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, session: SessionDep):
    project = load_project(session, project_id)
    if body.name is not None:
        project.name = body.name.strip()
    if body.description is not None:
        project.description = body.description.strip()
    session.commit()
    return project_service.to_out(session, project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: SessionDep, storage: StorageDep):
    project_service.delete_project(session, storage, load_project(session, project_id))
    session.commit()
    return Response(status_code=204)


@router.post("/{project_id}/duplicate", response_model=ProjectOut, status_code=201)
def duplicate_project(project_id: str, session: SessionDep, storage: StorageDep):
    copy = project_service.duplicate_project(session, storage, load_project(session, project_id))
    session.commit()
    return project_service.to_out(session, copy)


@router.get("/{project_id}/assets", response_model=list[AssetOut])
def list_project_assets(
    project_id: str, session: SessionDep, kind: str | None = None, all_versions: bool = False
):
    load_project(session, project_id)
    return asset_service.list_assets(
        session, project_id=project_id, kind=kind, latest_only=not all_versions, limit=500
    )


@router.get("/{project_id}/jobs", response_model=list[JobOut])
def list_project_jobs(project_id: str, session: SessionDep):
    load_project(session, project_id)
    return list(
        session.scalars(
            select(Job)
            .where(Job.project_id == project_id)
            .order_by(Job.created_at.desc())
            .limit(50)
        )
    )


@router.get("/{project_id}/export")
def export_project(project_id: str, session: SessionDep, storage: StorageDep):
    project = load_project(session, project_id)
    bundle = project_service.export_bundle(session, storage, project)
    filename = f"{project_service.slugify(project.name, 'project')}.zip"
    return Response(
        bundle,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
