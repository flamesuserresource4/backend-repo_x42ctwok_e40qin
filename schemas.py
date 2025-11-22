"""
Database Schemas for RaigadFarmBazaar

Each Pydantic model below represents a MongoDB collection.
Collection name is the lowercase class name.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Unique email address")
    password_hash: str = Field(..., description="Hashed password")
    role: str = Field(..., pattern="^(owner|buyer)$", description="User role: owner or buyer")
    phone: Optional[str] = Field(None, description="Contact phone number")
    is_active: bool = Field(True, description="Whether user is active")

class Property(BaseModel):
    title: str = Field(..., description="Listing title")
    description: Optional[str] = Field(None, description="Listing description")
    price: float = Field(..., ge=0, description="Price in INR")
    location: str = Field(..., description="City/District/Area")
    size_sqft: Optional[float] = Field(None, ge=0, description="Plot/house size in sqft")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    owner_id: str = Field(..., description="Reference to user _id (string)")
    owner_name: str = Field(..., description="Owner's display name")
    owner_phone: Optional[str] = Field(None, description="Owner contact")
    status: str = Field("available", pattern="^(available|locked|sold)$", description="Availability status")
    locked_by: Optional[str] = Field(None, description="User id who locked")

class Message(BaseModel):
    property_id: str = Field(..., description="Property _id")
    sender_id: str = Field(..., description="Buyer user id")
    owner_id: str = Field(..., description="Owner user id")
    content: str = Field(..., min_length=1, max_length=2000)

class Lock(BaseModel):
    property_id: str = Field(..., description="Property _id")
    buyer_id: str = Field(..., description="Buyer user id")
    owner_id: str = Field(..., description="Owner user id")
    note: Optional[str] = Field(None, description="Optional note from buyer")
