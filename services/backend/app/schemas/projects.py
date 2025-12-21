from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# Dataset schema (for responses)
class Dataset(BaseModel):
    id: str
    user_id: str
    project_id: Optional[str] = None
    filename: str
    file_url: str
    file_type: str
    file_size: Optional[int] = None
    status: str
    metadata: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Document schema (for responses)
class Document(BaseModel):
    id: str
    user_id: str
    project_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    file_url: str
    file_type: str
    file_size: Optional[int] = None
    metadata: Optional[dict] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Project create schema (for POST requests)
class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None


# Project update schema (for PUT requests)
class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


# Project schema (for responses)
class Project(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Project bundle schema (project + all related datasets and documents)
class ProjectBundle(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    datasets: List[Dataset] = []
    documents: List[Document] = []

    class Config:
        from_attributes = True
