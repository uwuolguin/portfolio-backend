from sqlalchemy import Column, String, Text, DateTime, ForeignKey,Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "proveo"}
    
    uuid = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    hashed_password = Column(Text, nullable=False)
    role = Column(String(20), nullable=False, server_default='user')
    email_verified = Column(Boolean, nullable=False, server_default='false')
    verification_token = Column(Text, nullable=True) 
    verification_token_expires = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": "proveo"}
    
    uuid = Column(UUID(as_uuid=True), primary_key=True)
    name_es = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class Commune(Base):
    __tablename__ = "communes"
    __table_args__ = {"schema": "proveo"}
    
    uuid = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class Company(Base):
    __tablename__ = "companies"
    __table_args__ = {"schema": "proveo"}
    
    uuid = Column(UUID(as_uuid=True), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey("proveo.users.uuid"), nullable=False)
    product_uuid = Column(UUID(as_uuid=True), ForeignKey("proveo.products.uuid"), nullable=False)
    commune_uuid = Column(UUID(as_uuid=True), ForeignKey("proveo.communes.uuid"), nullable=False)
    name = Column(String(100), nullable=False)
    description_es = Column(String(100), nullable=False)
    description_en = Column(String(100), nullable=False)
    address = Column(String(100), nullable=False)
    phone = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    image_url = Column(String(10000), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class UserDeleted(Base):
    __tablename__ = "users_deleted"
    __table_args__ = {"schema": "proveo"}
    
    uuid = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    hashed_password = Column(Text, nullable=False)
    role = Column(String(20), nullable=False, server_default='user')  
    email_verified = Column(Boolean, nullable=False, server_default='false') 
    created_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class ProductDeleted(Base):
    __tablename__ = "products_deleted"
    __table_args__ = {"schema": "proveo"}
    
    uuid = Column(UUID(as_uuid=True), primary_key=True)
    name_es = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class CommuneDeleted(Base):
    __tablename__ = "communes_deleted"
    __table_args__ = {"schema": "proveo"}
    
    uuid = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class CompanyDeleted(Base):
    __tablename__ = "companies_deleted"
    __table_args__ = {"schema": "proveo"}
    
    uuid = Column(UUID(as_uuid=True), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), nullable=False)
    product_uuid = Column(UUID(as_uuid=True), nullable=False)
    commune_uuid = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(100), nullable=False)
    description_es = Column(String(100), nullable=False)
    description_en = Column(String(100), nullable=False)
    address = Column(String(100), nullable=False)
    phone = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    image_url = Column(String(10000), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())