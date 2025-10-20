from pydantic import BaseModel, EmailStr, Field, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional
from fastapi import Form

class CompanyCreate(BaseModel):
    product_uuid: UUID
    commune_uuid: UUID
    name: str
    description_es: Optional[str]
    description_en: Optional[str]
    address: str
    phone: str
    email: EmailStr
    image_url: str
    lang: str

    @model_validator(mode="after")
    def check_at_least_one_description(self):
        if not self.description_es and not self.description_en:
            raise ValueError("At least one description (description_es or description_en) must be provided")
        return self

class CompanyUpdate(BaseModel):
    product_uuid: Optional[UUID]
    commune_uuid: Optional[UUID]
    name: Optional[str]
    description_es: Optional[str]
    description_en: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    email: Optional[EmailStr]
    image_url: Optional[str]
    lang: Optional[str]

    @model_validator(mode='after')
    def validate_description_and_lang(self):
        if (self.description_es or self.description_en) and not self.lang:
            raise ValueError("lang field is required when updating descriptions")
        if self.lang and self.lang not in ["es", "en"]:
            raise ValueError("lang must be either 'es' or 'en'")
        return self

    @classmethod
    def as_form(
        cls,
        product_uuid: Optional[UUID] = Form(None),
        commune_uuid: Optional[UUID] = Form(None),
        name: Optional[str] = Form(None),
        description_es: Optional[str] = Form(None),
        description_en: Optional[str] = Form(None),
        address: Optional[str] = Form(None),
        phone: Optional[str] = Form(None),
        email: Optional[EmailStr] = Form(None),
        image_url: Optional[str] = Form(None),
        lang: Optional[str] = Form(None),
    ):
        return cls(
            product_uuid=product_uuid,
            commune_uuid=commune_uuid,
            name=name,
            description_es=description_es,
            description_en=description_en,
            address=address,
            phone=phone,
            email=email,
            image_url=image_url,
            lang=lang,
        )

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
