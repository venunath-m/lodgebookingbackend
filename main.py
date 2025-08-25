import os
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import text,Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint,DateTime
from sqlalchemy.orm import relationship, Session
from sqlalchemy import JSON
from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

# ✅ Import from database.py
from database import Base, engine, SessionLocal, get_db  
from fastapi import UploadFile, File
import uuid
from fastapi import Form
from fastapi import Query
from fastapi.responses import JSONResponse
from datetime import datetime, date
# ---------- Config ----------
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change_me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

_allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOW_ORIGINS = _allowed if _allowed else []

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

logging.basicConfig(level=logging.INFO)
from fastapi.staticfiles import StaticFiles

# ---------- Models ----------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="user")  # user | admin
    password_hash = Column(String, nullable=False)
    allowed_features = Column(JSON, default=[])
    bookings = relationship("Booking", back_populates="user")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    description = Column(String, default="")
    imageUrl = Column(String, default="")
    status = Column(String, default="available")  # <-- new field
    bookings = relationship("Booking", back_populates="room")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    userId = Column(Integer, ForeignKey("users.id"), nullable=False)
    roomId = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    startDate = Column(Date, nullable=False)
    endDate = Column(Date, nullable=False)
    males = Column(Integer, default=0)
    females = Column(Integer, default=0)
    documentUrl = Column(String, nullable=True)
    status = Column(String, default="confirmed")  # confirmed|cancelled
    user = relationship("User", back_populates="bookings")
    room = relationship("Room", back_populates="bookings")
    services = relationship("BookingService", back_populates="booking", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("roomId", "startDate", "endDate", name="uq_room_dates"),)


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)   # Breakfast, Laundry, Spa
    price = Column(Float, nullable=False)

class BookingService(Base):
    __tablename__ = "booking_services"
    id = Column(Integer, primary_key=True)
    bookingId = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    serviceId = Column(Integer, ForeignKey("services.id"), nullable=False)
    quantity = Column(Integer, default=1)

    # Renamed to match schema
    service_date = Column(Date, default=date.today)  
    service_time = Column(DateTime, default=datetime.utcnow)  

    booking = relationship("Booking", back_populates="services")
    service = relationship("Service")

class RoomService(Base):
    __tablename__ = "room_services"
    id = Column(Integer, primary_key=True)
    roomId = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    serviceId = Column(Integer, ForeignKey("services.id"), nullable=False)
    service = relationship("Service")
    room = relationship("Room")


# ---------- Schemas ----------
class RoomOut(BaseModel):
    id: int
    name: str
    type: str
    price: float
    description: str
    imageUrl: str
    class Config: orm_mode = True

class RoomIn(BaseModel):
    name: str
    type: str
    price: float
    description: Optional[str] = ""
    imageUrl: Optional[str] = ""

class BookingCreate(BaseModel):
    roomId: int
    startDate: date
    endDate: date

class ServiceOut(BaseModel):
    id: int
    name: str
    price: float
    class Config: orm_mode = True

class AddServiceIn(BaseModel):
    serviceId: int
    quantity: int = 1

class BookingServiceOut(BaseModel):
    id: int
    service: ServiceOut
    quantity: int
    service_date: date
    service_time: datetime

    class Config:
        orm_mode = True


class BookingOut(BaseModel):
    id: int
    room: RoomOut
    startDate: date
    endDate: date
    status: str
    males: int
    females: int
    documentUrl: Optional[str] = None
    services: List[BookingServiceOut] = []
    class Config:
        orm_mode = True


# Auth schemas
class RegisterIn(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: Optional[str] = "user"
    allowed_features: Optional[List[str]] = [] 

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
os.makedirs("uploads", exist_ok=True)
UPLOADS_DIR = "uploads"
# ---------- App ----------
app = FastAPI(title="Lodge Booking API (Secure)")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # exact URLs only
    allow_credentials=True,       # needed for Authorization header
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Auth helpers ----------
def hash_password(p: str) -> str:
    return pwd_context.hash(p)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except JWTError:
        raise credentials_exception
    user = db.get(User, user_id)
    if not user:
        raise credentials_exception
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
@app.get("/uploads/files")
def get_uploaded_files():
    if not os.path.exists(UPLOADS_DIR):
        return {"files": []}

    # Only include image files
    images = [
        f for f in os.listdir(UPLOADS_DIR)
        if os.path.isfile(os.path.join(UPLOADS_DIR, f)) and f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))
    ]
    # Optional: add full URL
    base_url = "https://lodgebookingbackend.onrender.com/uploads"  # replace with your actual URL
    images = [f"{base_url}/{f}" for f in images]
    return {"files": images}

# ---------- Auth Endpoints ----------
@app.post("/auth/register", status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")

    u = User(
        email=payload.email,
        name=payload.name,
        role=payload.role,
        allowed_features=payload.allowed_features if payload.role == "user" else [],
        password_hash=hash_password(payload.password)
    )
    db.add(u)
    db.commit()
    return {"message": "Registered successfully"}



@app.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenOut(access_token=token)

# ---------- Business Endpoints (secured) ----------

@app.get("/rooms", response_model=List[RoomOut])
def list_rooms(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Room).all()

@app.post("/admin/rooms", response_model=RoomOut)
def create_room(
    name: str = Form(...),
    type: str = Form(...),
    price: float = Form(...),
    description: Optional[str] = Form(""),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin)
):
    image_url = ""
    if image:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        ext = os.path.splitext(image.filename)[1]
        filename = f"{uuid.uuid4().hex}{ext}"  # only uuid.ext
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(image.file.read())
        image_url = f"/uploads/{filename}"

    
    r = Room(name=name, type=type, price=price, description=description, imageUrl=image_url)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@app.put("/admin/rooms/{room_id}", response_model=RoomOut)
def update_room(
    room_id: int,
    name: Optional[str] = Form(None),
    type: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    description: Optional[str] = Form(None),
    status: Optional[str] = Form(None),  # <-- add this
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin)
):
    r = db.get(Room, room_id)
    if not r: 
        raise HTTPException(404, "Room not found")
    
    if name: r.name = name
    if type: r.type = type
    if price: r.price = price
    if description: r.description = description    
    if status: r.status = status  # <-- handle status
    if image:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        ext = os.path.splitext(image.filename)[1]
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(image.file.read())
        r.imageUrl = f"/uploads/{filename}"

    db.commit()
    db.refresh(r)
    return r


@app.delete("/admin/rooms/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = db.get(Room, room_id)
    if not r: raise HTTPException(404, "Room not found")
    db.delete(r); db.commit()
    return {"ok": True}

@app.post("/bookings", response_model=BookingOut)
def create_booking(
    roomId: int = Form(...),
    startDate: date = Form(...),
    endDate: date = Form(...),
    males: int = Form(0),
    females: int = Form(0),
    document: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = db.get(Room, roomId)
    if not room:
        raise HTTPException(404, "Room not found")

    # handle file upload
    document_url = None
    if document:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        ext = os.path.splitext(document.filename)[1]
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(document.file.read())
        document_url = f"/uploads/{filename}"

    booking = Booking(
        userId=current_user.id,
        roomId=roomId,
        startDate=startDate,
        endDate=endDate,
        males=males,
        females=females,
        documentUrl=document_url,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking

@app.put("/bookings/{booking_id}", response_model=BookingOut)
def update_booking(
    booking_id: int,
    roomId: Optional[int] = Form(None),
    startDate: Optional[date] = Form(None),
    endDate: Optional[date] = Form(None),
    males: Optional[int] = Form(None),
    females: Optional[int] = Form(None),
    document: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking or booking.userId != current_user.id:
        raise HTTPException(404, "Booking not found")

    if roomId:
        room = db.get(Room, roomId)
        if not room:
            raise HTTPException(404, "Room not found")
        booking.roomId = roomId
    if startDate: booking.startDate = startDate
    if endDate: booking.endDate = endDate
    if males is not None: booking.males = males
    if females is not None: booking.females = females

    if document:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        ext = os.path.splitext(document.filename)[1]
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(document.file.read())
        booking.documentUrl = f"/uploads/{filename}"

    db.commit()
    db.refresh(booking)
    return booking

@app.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking or booking.userId != current_user.id:
        raise HTTPException(404, "Booking not found")

    booking.status = "cancelled"
    db.commit()
    db.refresh(booking)
    return booking

@app.get("/bookings/me")
def my_bookings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
):
    q = db.query(Booking).filter(Booking.userId == current_user.id)

    if from_date:
        q = q.filter(Booking.startDate >= from_date)
    if to_date:
        q = q.filter(Booking.endDate <= to_date)

    bookings = q.order_by(Booking.startDate.desc()).all()

    return {
        "items": bookings
    }
# ---------- Service Management ----------

@app.post("/admin/services", response_model=ServiceOut)
def create_service(payload: ServiceOut, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    # Prevent duplicate service names
    if db.query(Service).filter(Service.name == payload.name).first():
        raise HTTPException(400, "Service with this name already exists")
    s = Service(name=payload.name, price=payload.price)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@app.put("/admin/services/{service_id}", response_model=ServiceOut)
def update_service(service_id: int, payload: ServiceOut, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = db.get(Service, service_id)
    if not s: 
        raise HTTPException(404, "Service not found")
    # Optional: check if name is used by another service
    if db.query(Service).filter(Service.name == payload.name, Service.id != service_id).first():
        raise HTTPException(400, "Service with this name already exists")
    s.name = payload.name
    s.price = payload.price
    db.commit()
    db.refresh(s)
    return s


@app.delete("/admin/services/{service_id}")
def delete_service(service_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = db.get(Service, service_id)
    if not s: 
        raise HTTPException(404, "Service not found")
    
    # Check for linked room assignments or bookings
    linked_rooms = db.query(RoomService).filter_by(serviceId=service_id).count()
    linked_bookings = db.query(BookingService).filter_by(serviceId=service_id).count()
    if linked_rooms > 0 or linked_bookings > 0:
        raise HTTPException(400, "Cannot delete service: assigned to rooms or bookings exist")
    
    db.delete(s)
    db.commit()
    return {"ok": True}


# ---------- Room-Service Assignment ----------

@app.post("/admin/rooms/{room_id}/services")
def assign_service_to_room(
    room_id: int, 
    serviceId: int = Form(...), 
    db: Session = Depends(get_db), 
    _: User = Depends(require_admin)
):
    room = db.get(Room, room_id)
    if not room: 
        raise HTTPException(404, "Room not found")
    
    svc = db.get(Service, serviceId)
    if not svc: 
        raise HTTPException(404, "Service not found")
    
    # Check if already assigned
    exists = db.query(RoomService).filter_by(roomId=room_id, serviceId=serviceId).first()
    if exists:
        return {"message": "Service already assigned"}
    
    rs = RoomService(roomId=room_id, serviceId=serviceId)
    db.add(rs)
    db.commit()
    db.refresh(rs)
    return rs


@app.delete("/admin/rooms/{room_id}/services/{service_id}")
def remove_service_from_room(
    room_id: int, 
    service_id: int, 
    db: Session = Depends(get_db), 
    _: User = Depends(require_admin)
):
    rs = db.query(RoomService).filter_by(roomId=room_id, serviceId=service_id).first()
    if not rs: 
        raise HTTPException(404, "Assignment not found")
    
    # Optional: prevent removal if bookings exist
    active_bookings = (
        db.query(BookingService)
        .join(Booking, Booking.id == BookingService.bookingId)
        .filter(Booking.roomId == room_id, BookingService.serviceId == service_id)
        .count()
    )
    if active_bookings > 0:
        raise HTTPException(400, "Cannot remove service: bookings already exist for this room/service")
    
    db.delete(rs)
    db.commit()
    return {"ok": True}


@app.get("/rooms/{room_id}/services", response_model=List[ServiceOut])
def get_services_for_room(room_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    services = (
        db.query(Service)
        .join(RoomService, RoomService.serviceId == Service.id)
        .filter(RoomService.roomId == room_id)
        .all()
    )
    return services


@app.get("/services", response_model=List[ServiceOut])
def list_services(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Service).all()


# ---------- Booking-Service ----------

@app.post("/bookings/{booking_id}/services", response_model=BookingServiceOut)
def add_service(
    booking_id: int,
    payload: AddServiceIn,
    service_date: Optional[date] = Form(None),
    service_time: Optional[datetime] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking or booking.userId != current_user.id:
        raise HTTPException(404, "Booking not found")
    
    # Validate room-service mapping
    room_service = db.query(RoomService).filter_by(
        roomId=booking.roomId, serviceId=payload.serviceId
    ).first()
    if not room_service:
        raise HTTPException(400, "Service not allowed for this room")
    
    # ✅ Use consistent names with model
    item = BookingService(
        bookingId=booking_id,
        serviceId=payload.serviceId,
        quantity=payload.quantity,
        service_date=service_date or date.today(),
        service_time=service_time or datetime.utcnow()
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
@app.put("/bookings/{booking_id}/services/{service_id}", response_model=BookingServiceOut)
def update_booking_service(
    booking_id: int,
    service_id: int,
    quantity: Optional[int] = Form(None),
    service_date: Optional[date] = Form(None),
    service_time: Optional[datetime] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking or booking.userId != current_user.id:
        raise HTTPException(404, "Booking not found")
    
    item = db.query(BookingService).filter_by(bookingId=booking_id, serviceId=service_id).first()
    if not item:
        raise HTTPException(404, "Service not found in this booking")
    
    if quantity is not None:
        item.quantity = quantity
    if service_date is not None:
        item.service_date = service_date
    if service_time is not None:
        item.service_time = service_time

    db.commit()
    db.refresh(item)
    return item
@app.delete("/bookings/{booking_id}/services/{service_id}")
def delete_booking_service(
    booking_id: int,
    service_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking or booking.userId != current_user.id:
        raise HTTPException(404, "Booking not found")

    item = db.query(BookingService).filter_by(bookingId=booking_id, serviceId=service_id).first()
    if not item:
        raise HTTPException(404, "Service not found in this booking")
    
    db.delete(item)
    db.commit()
    return {"ok": True, "message": "Service removed from booking"}



@app.get("/health/db")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        logging.error(f"DB Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")


# ---------- Bootstrap (tables + seed) ----------
@app.on_event("startup")
def startup():
    logging.info("Creating tables & seeding data...")
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        db.execute(text("""
        ALTER TABLE rooms
        ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'available';
    """))
        # Ensure allowed_features exists (users table)
        db.execute(text("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS allowed_features JSON DEFAULT '[]';
        """))

        # Ensure new booking columns exist
        db.execute(text("""
            ALTER TABLE bookings
            ADD COLUMN IF NOT EXISTS males INT DEFAULT 0;
        """))
        db.execute(text("""
            ALTER TABLE bookings
            ADD COLUMN IF NOT EXISTS females INT DEFAULT 0;
        """))
        db.execute(text("""
            ALTER TABLE bookings
            ADD COLUMN IF NOT EXISTS "documentUrl" VARCHAR;
        """))

        db.commit()

        # Seed users/rooms/services
        if not db.query(User).count():
            admin = User(
                email="admin@hotel.com", name="Admin", role="admin",
                password_hash=hash_password("admin123")
            )
            guest = User(
                email="guest@hotel.com", name="Guest", role="user",
                password_hash=hash_password("guest123")
            )
            db.add_all([admin, guest])

        if not db.query(Room).count():
            db.add_all([
                Room(name="Deluxe 101", type="Deluxe", price=89.0, description="City view, queen bed", status="available"),
                Room(name="Suite 201", type="Suite", price=159.0, description="King bed, lounge access", status="available"),
                # ... other rooms
            ])

        if not db.query(Service).count():
            db.add_all([
                Service(name="Breakfast", price=8.0),
                Service(name="Laundry", price=5.0),
                Service(name="Spa", price=35.0),
                Service(name="Cleaning", price=0.0),
            ])
        db.commit()

