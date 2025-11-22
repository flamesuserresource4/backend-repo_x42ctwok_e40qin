import os
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId
from passlib.context import CryptContext

from database import db, create_document, get_documents
from schemas import User as UserSchema, Property as PropertySchema, Message as MessageSchema, Lock as LockSchema

app = FastAPI(title="RaigadFarmBazaar API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Utility helpers

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


# Auth models
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str  # owner or buyer
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    role: str
    phone: Optional[str] = None


@app.get("/")
def read_root():
    return {"name": "RaigadFarmBazaar", "status": "ok"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ================ AUTH =================
@app.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest):
    # ensure unique email
    existing = db["user"].find_one({"email": payload.email}) if db else None
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = {
        "name": payload.name,
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "role": payload.role if payload.role in ["owner", "buyer"] else "buyer",
        "phone": payload.phone,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = db["user"].insert_one(user_doc)
    return AuthResponse(
        user_id=str(result.inserted_id),
        name=user_doc["name"],
        email=user_doc["email"],
        role=user_doc["role"],
        phone=user_doc.get("phone"),
    )


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    user = db["user"].find_one({"email": payload.email}) if db else None
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return AuthResponse(
        user_id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        role=user["role"],
        phone=user.get("phone"),
    )


# ================ PROPERTIES ================
class CreatePropertyRequest(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    location: str
    size_sqft: Optional[float] = None
    images: Optional[List[str]] = []
    owner_id: str
    owner_name: str
    owner_phone: Optional[str] = None


class PropertyResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    price: float
    location: str
    size_sqft: Optional[float]
    images: List[str]
    owner_id: str
    owner_name: str
    owner_phone: Optional[str]
    status: str
    locked_by: Optional[str]


@app.post("/properties", response_model=PropertyResponse)
def create_property(payload: CreatePropertyRequest):
    # Verify owner exists and is owner role
    owner = db["user"].find_one({"_id": to_object_id(payload.owner_id)})
    if not owner or owner.get("role") != "owner":
        raise HTTPException(status_code=400, detail="Invalid owner")

    prop = {
        "title": payload.title,
        "description": payload.description,
        "price": payload.price,
        "location": payload.location,
        "size_sqft": payload.size_sqft,
        "images": payload.images or [],
        "owner_id": payload.owner_id,
        "owner_name": payload.owner_name,
        "owner_phone": payload.owner_phone,
        "status": "available",
        "locked_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = db["property"].insert_one(prop)
    prop["_id"] = result.inserted_id
    return PropertyResponse(
        id=str(prop["_id"]),
        title=prop["title"],
        description=prop.get("description"),
        price=prop["price"],
        location=prop["location"],
        size_sqft=prop.get("size_sqft"),
        images=prop.get("images", []),
        owner_id=prop["owner_id"],
        owner_name=prop["owner_name"],
        owner_phone=prop.get("owner_phone"),
        status=prop["status"],
        locked_by=prop.get("locked_by"),
    )


@app.get("/properties", response_model=List[PropertyResponse])
def list_properties(q: Optional[str] = None, status: Optional[str] = None):
    filt = {}
    if q:
        # Simple text search across title and location
        filt["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"location": {"$regex": q, "$options": "i"}},
        ]
    if status:
        filt["status"] = status
    props = list(db["property"].find(filt).sort("created_at", -1))
    out: List[PropertyResponse] = []
    for p in props:
        out.append(PropertyResponse(
            id=str(p["_id"]),
            title=p.get("title", ""),
            description=p.get("description"),
            price=p.get("price", 0.0),
            location=p.get("location", ""),
            size_sqft=p.get("size_sqft"),
            images=p.get("images", []),
            owner_id=p.get("owner_id", ""),
            owner_name=p.get("owner_name", ""),
            owner_phone=p.get("owner_phone"),
            status=p.get("status", "available"),
            locked_by=p.get("locked_by"),
        ))
    return out


# ================ CONTACT & LOCK ================
class ContactRequest(BaseModel):
    property_id: str
    buyer_id: str
    message: str


@app.post("/properties/contact")
def contact_owner(payload: ContactRequest):
    # Validate property and buyer
    prop = db["property"].find_one({"_id": to_object_id(payload.property_id)})
    buyer = db["user"].find_one({"_id": to_object_id(payload.buyer_id)})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    msg_doc = {
        "property_id": payload.property_id,
        "sender_id": payload.buyer_id,
        "owner_id": prop["owner_id"],
        "content": payload.message,
        "created_at": datetime.now(timezone.utc),
    }
    db["message"].insert_one(msg_doc)
    return {"ok": True}


class LockRequest(BaseModel):
    property_id: str
    buyer_id: str
    note: Optional[str] = None


@app.post("/properties/lock")
def lock_property(payload: LockRequest):
    prop = db["property"].find_one({"_id": to_object_id(payload.property_id)})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    if prop.get("status") == "locked":
        raise HTTPException(status_code=400, detail="Property already locked")
    if prop.get("status") == "sold":
        raise HTTPException(status_code=400, detail="Property already sold")

    # ensure buyer exists
    buyer = db["user"].find_one({"_id": to_object_id(payload.buyer_id)})
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    db["property"].update_one(
        {"_id": prop["_id"]},
        {"$set": {"status": "locked", "locked_by": payload.buyer_id, "updated_at": datetime.now(timezone.utc)}},
    )

    lock_doc = {
        "property_id": payload.property_id,
        "buyer_id": payload.buyer_id,
        "owner_id": prop["owner_id"],
        "note": payload.note,
        "created_at": datetime.now(timezone.utc),
    }
    db["lock"].insert_one(lock_doc)
    return {"ok": True}


# ================ SCHEMA EXPOSURE (for DB viewer) ================
@app.get("/schema")
def get_schema():
    # Read class docstrings or simple names
    return {
        "user": UserSchema.model_json_schema(),
        "property": PropertySchema.model_json_schema(),
        "message": MessageSchema.model_json_schema(),
        "lock": LockSchema.model_json_schema(),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
