from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class CompanyResponse(BaseModel):
    uuid: UUID
    user_uuid: UUID
    product_uuid: UUID
    commune_uuid: UUID
    name: str
    description_es: str
    description_en: str
    address: str
    phone: str
    email: str
    image_url: str
    created_at: datetime
    updated_at: datetime
    user_name: str
    user_email: str
    product_name_es: str
    product_name_en: str
    commune_name: str

class CompanySearchResponse(BaseModel):
    name: str
    description: str
    address: str
    email: str
    phone: str
    img_url: str
    product_name: str
    commune_name: str
