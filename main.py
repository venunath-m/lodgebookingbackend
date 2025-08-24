import os
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import text,Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, Session

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

# ✅ Import from database.py
from database import Base, engine, SessionLocal, get_db  

# ---------- Config ----------
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change_me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

_allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
ALLOW_ORIGINS = _allowed if _allowed else ["*"]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

logging.basicConfig(level=logging.INFO)

# ---------- Models ----------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="user")  # user | admin
    password_hash = Column(String, nullable=False)
    bookings = relationship("Booking", back_populates="user")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)      # e.g., Deluxe 101
    type = Column(String, nullable=False)      # Deluxe, Suite, etc.
    price = Column(Float, nullable=False)      # per night
    description = Column(String, default="")
    imageUrl = Column(String, default="")
    bookings = relationship("Booking", back_populates="room")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    userId = Column(Integer, ForeignKey("users.id"), nullable=False)
    roomId = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    startDate = Column(Date, nullable=False)
    endDate = Column(Date, nullable=False)
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
    booking = relationship("Booking", back_populates="services")
    service = relationship("Service")

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
    class Config: orm_mode = True

class BookingOut(BaseModel):
    id: int
    room: RoomOut
    startDate: date
    endDate: date
    status: str
    services: List[BookingServiceOut] = []
    class Config: orm_mode = True

# Auth schemas
class RegisterIn(BaseModel):
    email: EmailStr
    name: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

# ---------- App ----------
app = FastAPI(title="Lodge Booking API (Secure)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
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

# ---------- Auth Endpoints ----------
@app.post("/auth/register", status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")
    u = User(email=payload.email, name=payload.name, role="user", password_hash=hash_password(payload.password))
    db.add(u); db.commit()
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
def create_room(room: RoomIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = Room(**room.dict())
    db.add(r); db.commit(); db.refresh(r)
    return r

@app.put("/admin/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: int, room: RoomIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = db.get(Room, room_id)
    if not r: raise HTTPException(404, "Room not found")
    for k, v in room.dict().items(): setattr(r, k, v)
    db.commit(); db.refresh(r)
    return r

@app.delete("/admin/rooms/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = db.get(Room, room_id)
    if not r: raise HTTPException(404, "Room not found")
    db.delete(r); db.commit()
    return {"ok": True}

@app.post("/bookings", response_model=BookingOut)
def create_booking(payload: BookingCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    room = db.get(Room, payload.roomId)
    if not room: raise HTTPException(404, "Room not found")
    b = Booking(userId=current_user.id, roomId=payload.roomId, startDate=payload.startDate, endDate=payload.endDate)
    db.add(b); db.commit(); db.refresh(b)
    return b

@app.get("/bookings/me", response_model=List[BookingOut])
def my_bookings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Booking).filter(Booking.userId == current_user.id).all()

@app.get("/services", response_model=List[ServiceOut])
def list_services(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Service).all()

@app.post("/bookings/{booking_id}/services", response_model=BookingServiceOut)
def add_service(booking_id: int, payload: AddServiceIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking or booking.userId != current_user.id:
        raise HTTPException(404, "Booking not found")
    svc = db.get(Service, payload.serviceId)
    if not svc: raise HTTPException(404, "Service not found")
    item = BookingService(bookingId=booking_id, serviceId=payload.serviceId, quantity=payload.quantity)
    db.add(item); db.commit(); db.refresh(item)
    return item


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
                Room(name="Deluxe 101", type="Deluxe", price=89.0, description="City view, queen bed"),
                Room(name="Suite 201", type="Suite", price=159.0, description="King bed, lounge access"),
            ])
        if not db.query(Service).count():
            db.add_all([
                Service(name="Breakfast", price=8.0),
                Service(name="Laundry", price=5.0),
                Service(name="Spa", price=35.0),
                Service(name="Cleaning", price=0.0),
            ])
        db.commit()
