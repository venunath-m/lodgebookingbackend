import os
import logging
from datetime import date, datetime, timedelta, time
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import func,cast,text,Column, Integer, String, Float, Date, Time,ForeignKey, UniqueConstraint,DateTime
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
from sqlalchemy import Boolean
from accounting.routes import router as accounting_router
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
class CashClosing(Base):
    __tablename__ = "cashclosing"

    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey("users.id"))
    denominations = Column(String)
    cashAmount = Column(Float)
    onlineAmount = Column(Float)
    upiAmount = Column(Float)
    cardAmount = Column(Float)
    systemAmount = Column(Float)
    difference = Column(Float)
    closingDate = Column(Date)

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    userId = Column(Integer, ForeignKey("users.id"), nullable=False)
    roomId = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    
    # Existing fields
    startDate = Column(Date, nullable=False)
    endDate = Column(Date, nullable=False)
    males = Column(Integer, default=0)
    females = Column(Integer, default=0)
    documentUrl = Column(String, nullable=True)
    status = Column(String, default="confirmed")

    # ✅ New fields
    name = Column(String, nullable=True)
    mobile = Column(String, nullable=True)
    checkInDate = Column(Date, nullable=True)
    checkInTime = Column(Time, nullable=True)
    checkOutDate = Column(Date, nullable=True)
    checkOutTime = Column(Time, nullable=True)
    customerGstNo = Column(String, nullable=True)
    roomNo = Column(String, nullable=True)
    numberOfDates = Column(Integer, default=0)
    totalNoPeople = Column(Integer, default=0)
    bookingSource = Column(String, nullable=False)
    paymentMethod = Column(String, nullable=False)
    address = Column(String, nullable=False)
    safe = Column(Boolean, default=False)
    bookingNumber = Column(String, nullable=False)

    # Relationships
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
    class Config: from_attributes = True

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
    class Config: from_attributes = True
class ServiceCreate(BaseModel):
    name: str
    price: float    

class AddServiceIn(BaseModel):
    serviceId: int
    quantity: int = 1

class BookingServiceOut(BaseModel):
    id: int
    service: ServiceOut
    quantity: int
    service_date: date
    service_time: datetime

    class Config: from_attributes = True



class BookingOut(BaseModel):
    id: int
    name: Optional[str] = None
    mobile: Optional[str] = None
    checkInDate: Optional[date] = None
    checkInTime: Optional[time] = None
    checkOutDate: Optional[date] = None
    checkOutTime: Optional[time] = None
    customerGstNo: Optional[str] = None
    roomNo: Optional[str] = None
    numberOfDates: Optional[int] = None
    totalNoPeople: Optional[int] = None
    bookingSource: Optional[str] = None
    paymentMethod: Optional[str] = None
    address: Optional[str] = None
    safe: Optional[bool] = None
    bookingNumber: Optional[str] = None

    room: RoomOut
    startDate: date
    endDate: date
    status: str
    males: int
    females: int
    documentUrl: Optional[str] = None
    services: List[BookingServiceOut] = []

    model_config = {
        "from_attributes": True  # ✅ Pydantic v2 replacement for orm_mode
    }


class InvoiceItemIn(BaseModel):
    description: str
    quantity: int = 1
    unitPrice: float
    serviceId: Optional[int] = None

class InvoiceCreate(BaseModel):
    bookingId: int
    items: List[InvoiceItemIn]
    tax: float = 0.0
    discount: float = 0.0

class InvoiceUpdate(BaseModel):
    items: Optional[List[InvoiceItemIn]] = None
    tax: Optional[float] = None
    discount: Optional[float] = None
    reason: str


class InvoiceItemOut(BaseModel):
    id: int
    description: str
    quantity: int
    unitPrice: float
    subtotal: float
    class Config: from_attributes = True

class InvoiceIn(BaseModel):
    bookingId: int
    tax: float = 0
    discount: float = 0

class InvoiceOut(BaseModel):
    id: int
    bookingId: int
    totalAmount: float
    tax: float
    discount: float
    finalAmount: float
    items: List[InvoiceItemOut] = []
    createdBy: int
    createdAt: datetime
    updatedBy: Optional[int] = None
    updatedAt: Optional[datetime] = None
    reason: Optional[str] = None
    bookingNumber: Optional[str] = None   
    invoiceNumber: Optional[str] = None 
    class Config: from_attributes = True
 


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    bookingId = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    
    # Booking snapshot fields for printing
    customerName = Column(String, nullable=True)
    mobile = Column(String, nullable=True)
    roomNo = Column(String, nullable=True)
    roomName = Column(String, nullable=True)
    checkInDate = Column(Date, nullable=True)
    checkInTime = Column(Time, nullable=True)
    checkOutDate = Column(Date, nullable=True)
    checkOutTime = Column(Time, nullable=True)
    bookingSource = Column(String, nullable=True)
    paymentMethod = Column(String, nullable=True)
    address = Column(String, nullable=True)
    safe = Column(Boolean, default=False)
    gstNo = Column(String, nullable=True)
    numberOfDates = Column(Integer, default=0)
    totalNoPeople = Column(Integer, default=0)
    bookingNumber = Column(String, nullable=False)
    invoiceNumber = Column(String, nullable=False)


    totalAmount = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    finalAmount = Column(Float, default=0.0)

    createdBy = Column(Integer, ForeignKey("users.id"), nullable=False)
    updatedBy = Column(Integer, ForeignKey("users.id"), nullable=True)
    deletedBy = Column(Integer, ForeignKey("users.id"), nullable=True)

    reason = Column(String, default="")
    isDeleted = Column(Boolean, default=False)

    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, nullable=True)
    deletedAt = Column(DateTime, nullable=True)

    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    booking = relationship("Booking")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id = Column(Integer, primary_key=True)
    invoiceId = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    description = Column(String, nullable=False)  # Room name or service name
    quantity = Column(Integer, default=1)
    unitPrice = Column(Float, default=0.0)
    subtotal = Column(Float, default=0.0)
    serviceId = Column(Integer, ForeignKey("services.id"), nullable=True)  # optional
    
    invoice = relationship("Invoice", back_populates="items")




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
    allow_origins=[
        "http://localhost:5173",  # local dev
        "https://lodge-booking-frontend.vercel.app",
        "https://lodgebookingfrontend.onrender.com",
        "https://novaresidency.com",
        "https://www.novaresidency.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Auth helpers ----------
def generate_booking_number(db: Session) -> str:
    """Generate a sequential booking number like BK-00001"""
    last_booking = db.query(Booking).order_by(Booking.id.desc()).first()
    if last_booking and last_booking.bookingNumber:
        # Extract numeric part and increment
        try:
            last_number = int(last_booking.bookingNumber.split("-")[1])
            new_number = last_number + 1
        except:
            new_number = 1
    else:
        new_number = 1
    return f"BK-{new_number:05d}"  # Pads with zeros, e.g., BK-00001
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
def get_next_invoice_number(db: Session):
    last_id = db.execute(text("SELECT MAX(id) FROM invoices")).scalar()
    next_id = (last_id or 0) + 1
    return f"INV-{next_id:06d}"
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
    base_url = "https://api.novaresidency.com"  # replace with your actual URL
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



@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": str(user.id), "role": user.role})
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role     # ✅ send role to frontend
    }


# ---------- Business Endpoints (secured) ----------
@app.post("/cashclosing")
def save_cash_closing(data: dict, db: Session = Depends(get_db), user = Depends(get_current_user)):
    entry = CashClosing(
        userId=user.id,
        denominations=data["denominations"],
        cashAmount=data["cashAmount"],
        onlineAmount=data["onlineAmount"],
        upiAmount=data["upiAmount"],
        cardAmount=data["cardAmount"],
        systemAmount=data["systemAmount"],
        difference=data["difference"],
        closingDate=date.today()
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry



@app.get("/cashclosing")
def get_cash_report(dateFilter: str | None = None, page: int = 1, db: Session = Depends(get_db)):
    query = db.query(CashClosing)
    if dateFilter:
        query = query.filter(CashClosing.closingDate == dateFilter)

    page_size = 10
    total = query.count()
    data = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": data,
        "total": total,
        "page": page,
        "totalPages": (total + page_size - 1) // page_size
    }
@app.get("/cashclosing/daily-report")
def get_daily_payment_summary(dateFilter: str | None = None, db: Session = Depends(get_db)):
    if not dateFilter:
        dateFilter = str(date.today())

    # Query totals based on paymentMethod field in bookings table
    cash_total = db.query(func.sum(Booking.amount)).filter(
        Booking.paymentMethod == "cash",
        func.date(Booking.bookingDate) == dateFilter
    ).scalar() or 0

    upi_total = db.query(func.sum(Booking.amount)).filter(
        Booking.paymentMethod == "upi",
        func.date(Booking.bookingDate) == dateFilter
    ).scalar() or 0

    card_total = db.query(func.sum(Booking.amount)).filter(
        Booking.paymentMethod == "card",
        func.date(Booking.bookingDate) == dateFilter
    ).scalar() or 0

    online_total = db.query(func.sum(Booking.amount)).filter(
        Booking.paymentMethod == "online",
        func.date(Booking.bookingDate) == dateFilter
    ).scalar() or 0

    system_total = cash_total + upi_total + card_total + online_total

    # Get last saved cash closing (optional)
    last_close = db.query(CashClosing).filter(
        CashClosing.closingDate == dateFilter
    ).order_by(CashClosing.id.desc()).first()

    return {
        "date": dateFilter,
        "cashTotal": cash_total,
        "upiTotal": upi_total,
        "cardTotal": card_total,
        "onlineTotal": online_total,
        "systemTotal": system_total,
        "lastClosing": last_close
    }    
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
    name: Optional[str] = Form(None),
    mobile: Optional[str] = Form(None),
    checkInDate: Optional[date] = Form(None),
    checkInTime: Optional[time] = Form(None),
    checkOutDate: Optional[date] = Form(None),
    checkOutTime: Optional[time] = Form(None),
    customerGstNo: Optional[str] = Form(None),
    roomNo: Optional[str] = Form(None),
    numberOfDates: Optional[int] = Form(0),
    totalNoPeople: Optional[int] = Form(0),
    bookingSource: Optional[str] = Form(None),
    paymentMethod: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    safe: Optional[bool] = Form(False),
    bookingNumber: Optional[str] = Form(None),
    document: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = db.get(Room, roomId)
    if not room:
        raise HTTPException(404, "Room not found")

    # Handle document upload
    document_url = None
    if document:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        ext = os.path.splitext(document.filename)[1]
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(document.file.read())
        document_url = f"/uploads/{filename}"

    # Generate sequential booking number if not provided
    if not bookingNumber:
        bookingNumber = generate_booking_number(db)
    else:
        # Ensure uniqueness if provided manually
        existing = db.query(Booking).filter(Booking.bookingNumber == bookingNumber).first()
        if existing:
            raise HTTPException(400, f"Booking number {bookingNumber} already exists.")

    booking = Booking(
        userId=current_user.id,
        roomId=roomId,
        startDate=startDate,
        endDate=endDate,
        males=males,
        females=females,
        documentUrl=document_url,
        name=name,
        mobile=mobile,
        checkInDate=checkInDate,
        checkInTime=checkInTime,
        checkOutDate=checkOutDate,
        checkOutTime=checkOutTime,
        customerGstNo=customerGstNo,
        roomNo=roomNo,
        numberOfDates=numberOfDates,
        totalNoPeople=totalNoPeople,
        bookingSource=bookingSource,
        paymentMethod=paymentMethod,
        address=address,
        safe=safe,
        bookingNumber=bookingNumber
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
    name: Optional[str] = Form(None),
    mobile: Optional[str] = Form(None),
    checkInDate: Optional[date] = Form(None),
    checkInTime: Optional[str] = Form(None),
    checkOutDate: Optional[date] = Form(None),
    checkOutTime: Optional[str] = Form(None),
    customerGstNo: Optional[str] = Form(None),
    roomNo: Optional[str] = Form(None),
    numberOfDates: Optional[int] = Form(None),
    totalNoPeople: Optional[int] = Form(None),
    bookingSource: Optional[str] = Form(None),
    paymentMethod: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    safe: Optional[str] = Form(None),
    bookingNumber: Optional[str] = Form(None),
    document: Optional[UploadFile] = File(None),
    current_user: "User" = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking or booking.userId != current_user.id:
        raise HTTPException(404, "Booking not found")

    # Update numeric/date fields
    if roomId: booking.roomId = roomId
    if startDate: booking.startDate = startDate
    if endDate: booking.endDate = endDate
    if males is not None: booking.males = males
    if females is not None: booking.females = females

    # Update other fields dynamically
    for field, value in locals().items():
        if field in [
            "name", "mobile", "checkInDate", "checkInTime", "checkOutDate", "checkOutTime",
            "customerGstNo", "roomNo", "numberOfDates", "totalNoPeople", "bookingSource",
            "safe", "paymentMethod", "address"
        ] and value is not None:
            setattr(booking, field, value)

    # Handle bookingNumber update safely
    if bookingNumber:
        # Check uniqueness
        existing = db.query(Booking).filter(
            Booking.bookingNumber == bookingNumber,
            Booking.id != booking.id
        ).first()
        if existing:
            raise HTTPException(400, f"Booking number {bookingNumber} already exists.")
        booking.bookingNumber = bookingNumber

    # Handle document upload
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

@app.get("/bookings/me", response_model=List[BookingOut])
def my_bookings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
):
    q = db.query(Booking).filter(Booking.userId == current_user.id)

    if from_date:
        q = q.filter(Booking.startDate >= from_date)
    if to_date:
        q = q.filter(Booking.endDate <= to_date)

    bookings = q.order_by(Booking.startDate.desc()).all()
    return bookings
@app.get("/bookings/next-number")
def get_next_booking_number(db: Session = Depends(get_db)):

    # Get the last booking ordered by numeric part of bookingNumber
    last_booking = (
        db.query(Booking)
        .filter(Booking.bookingNumber.isnot(None))
        .order_by(
            cast(func.substr(Booking.bookingNumber, 4), Integer).desc()
        )
        .first()
    )

    if last_booking and last_booking.bookingNumber:
        prefix, num = last_booking.bookingNumber.split("-")
        next_num = str(int(num) + 1).zfill(len(num))  # preserves number length
        next_number = f"{prefix}-{next_num}"
    else:
        next_number = "BK-000001"  # First booking default

    return {"nextBookingNumber": next_number}


# ---------- Service Management ----------
@app.post("/invoices", response_model=dict)
def create_invoice(
    payload: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    booking = db.get(Booking, payload.bookingId)
    if not booking:
        raise HTTPException(404, "Booking not found")

    total_amount = 0.0
    invoice_items = []
    for i in payload.items:
        subtotal = i.quantity * i.unitPrice
        total_amount += subtotal
        invoice_items.append(InvoiceItem(
            description=i.description,
            quantity=i.quantity,
            unitPrice=i.unitPrice,
            subtotal=subtotal,
            serviceId=i.serviceId
        ))

    final_amount = total_amount + payload.tax - payload.discount

    # ✅ Get the next invoice number (Auto-Increment Format)
    next_invoice_number = get_next_invoice_number(db)

    # ✅ Create invoice with snapshot
    invoice = Invoice(
        bookingId=payload.bookingId,
        invoiceNumber=next_invoice_number,   # <--- ✅ USE NEW NUMBER
        totalAmount=total_amount,
        tax=payload.tax,
        discount=payload.discount,
        finalAmount=final_amount,
        createdBy=current_user.id,
        items=invoice_items,

        customerName=booking.name,
        mobile=booking.mobile,
        roomNo=booking.roomNo,
        roomName=booking.room.name if booking.room else None,
        checkInDate=booking.checkInDate,
        checkInTime=booking.checkInTime,
        checkOutDate=booking.checkOutDate,
        checkOutTime=booking.checkOutTime,
        bookingSource=booking.bookingSource,
        paymentMethod=booking.paymentMethod,
        address=booking.address,
        safe=booking.safe,
        bookingNumber=booking.bookingNumber,
        gstNo=booking.customerGstNo,
        numberOfDates=booking.numberOfDates,
        totalNoPeople=booking.totalNoPeople
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return {
        "invoiceId": invoice.id,
        "invoiceNumber": invoice.invoiceNumber,  # ✅ Return new number
        "finalAmount": invoice.finalAmount,
        "createdAt": invoice.createdAt,
        "customerName": invoice.customerName,
        "room": invoice.roomName,
        "items": [
            {
                "description": i.description,
                "quantity": i.quantity,
                "unitPrice": i.unitPrice,
                "subtotal": i.subtotal,
                "serviceId": i.serviceId
            } for i in invoice.items
        ]
    }


@app.put("/invoices/{invoice_id}", response_model=dict)
def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.isDeleted:
        raise HTTPException(404, "Invoice not found")

    if not payload.reason:
        raise HTTPException(400, "Reason is required for edit")

    # ✅ Handle item updates
    if payload.items is not None:
        invoice.items.clear()
        total_amount = 0.0
        for i in payload.items:
            subtotal = i.quantity * i.unitPrice
            total_amount += subtotal
            invoice.items.append(InvoiceItem(
                description=i.description,
                quantity=i.quantity,
                unitPrice=i.unitPrice,
                subtotal=subtotal,
                serviceId=i.serviceId
            ))
        invoice.totalAmount = total_amount

    # ✅ Update tax & discount
    if payload.tax is not None:
        invoice.tax = payload.tax
    if payload.discount is not None:
        invoice.discount = payload.discount

    # ✅ Recalculate
    invoice.finalAmount = invoice.totalAmount + invoice.tax - invoice.discount
    invoice.updatedBy = current_user.id
    invoice.updatedAt = datetime.utcnow()
    invoice.reason = payload.reason

    # ✅ Refresh booking snapshot (in case booking details changed)
    booking = db.get(Booking, invoice.bookingId)
    if booking:
        invoice.customerName = booking.name
        invoice.mobile = booking.mobile
        invoice.roomNo = booking.roomNo
        invoice.roomName = booking.room.name if booking.room else None
        invoice.checkInDate = booking.checkInDate
        invoice.checkInTime = booking.checkInTime
        invoice.checkOutDate = booking.checkOutDate
        invoice.checkOutTime = booking.checkOutTime
        invoice.bookingSource = booking.bookingSource
        invoice.paymentMedthod = booking.paymentMedthod
        invoice.address = booking.address
        invoice.safe = booking.safe
        invoice.bookingNumber = booking.bookingNumber
        invoice.invoiceNumber = invoice.invoiceNumber
        invoice.gstNo = booking.customerGstNo
        invoice.numberOfDates = booking.numberOfDates
        invoice.totalNoPeople = booking.totalNoPeople

    db.commit()
    db.refresh(invoice)

    # ✅ Return full updated invoice
    return {
        "invoiceId": invoice.id,
        "bookingId": invoice.bookingId,
        "user": current_user.id,
        "totalAmount": invoice.totalAmount,
        "tax": invoice.tax,
        "discount": invoice.discount,
        "finalAmount": invoice.finalAmount,
        "createdAt": invoice.createdAt,
        "updatedAt": invoice.updatedAt,
        "reason": invoice.reason,
        "isDeleted": invoice.isDeleted,

        # Booking snapshot
        "customerName": invoice.customerName,
        "mobile": invoice.mobile,
        "roomNo": invoice.roomNo,
        "room": invoice.roomName,
        "checkInDate": invoice.checkInDate,
        "checkOutDate": invoice.checkOutDate,
        "checkInTime": invoice.checkInTime,
        "checkOutTime": invoice.checkOutTime,
        "bookingSource": invoice.bookingSource,
        "paymentMethod": invoice.paymentMethod,
        "safe": invoice.safe,
        "bookingNumber": invoice.bookingNumber,
        "invoiceNumber": invoice.invoiceNumber,
        "gstNo": invoice.gstNo,
        "numberOfDates": invoice.numberOfDates,
        "totalNoPeople": invoice.totalNoPeople,

        # Invoice items
        "items": [
            {
                "description": i.description,
                "quantity": i.quantity,
                "unitPrice": i.unitPrice,
                "subtotal": i.subtotal,
                "serviceId": i.serviceId
            } for i in invoice.items
        ]
    }

@app.get("/invoices", response_model=List[dict])
def list_invoices(include_deleted: bool = False, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    query = db.query(Invoice)
    if not include_deleted:
        query = query.filter(Invoice.isDeleted == False)
    invoices = query.order_by(Invoice.createdAt.desc()).all()
    
    result = []
    for inv in invoices:
        result.append({
            "invoiceId": inv.id,
            "bookingId": inv.bookingId,
            "user": inv.createdBy,
            "totalAmount": inv.totalAmount,
            "tax": inv.tax,
            "discount": inv.discount,
            "finalAmount": inv.finalAmount,
            "createdAt": inv.createdAt,
            "updatedAt": inv.updatedAt,
            "deletedAt": inv.deletedAt,
            "reason": inv.reason,
            "isDeleted": inv.isDeleted,

            # ✅ Extended booking details
            "customerName": inv.booking.name if inv.booking else None,
            "mobile": inv.booking.mobile if inv.booking else None,
            "roomNo": inv.booking.roomNo if inv.booking else None,
            "checkInDate": inv.booking.checkInDate if inv.booking else None,
            "checkOutDate": inv.booking.checkOutDate if inv.booking else None,
            "checkInTime": inv.booking.checkInTime if inv.booking else None,
            "checkOutTime": inv.booking.checkOutTime if inv.booking else None,
            "bookingSource": inv.booking.bookingSource if inv.booking else None,
            "paymentMethod": inv.booking.paymentMethod if inv.booking else None,
            "address": inv.booking.address if inv.booking else None,
            "safe": inv.booking.safe if inv.booking else None,
            "bookingNumber": inv.booking.bookingNumber if inv.booking else None,
            "invoiceNumber": inv.invoiceNumber if inv.booking else None,
            "gstNo": inv.booking.customerGstNo if inv.booking else None,
            "numberOfDates": inv.booking.numberOfDates if inv.booking else None,
            "totalNoPeople": inv.booking.totalNoPeople if inv.booking else None,
            "room": inv.booking.room.name if inv.booking and inv.booking.room else None,

            "items": [
                {
                    "description": i.description,
                    "quantity": i.quantity,
                    "unitPrice": i.unitPrice,
                    "subtotal": i.subtotal,
                    "serviceId": i.serviceId
                }
                for i in inv.items
            ]
        })
    return result

@app.delete("/invoices/{invoice_id}")
def delete_invoice(invoice_id: int, reason: str = Form(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.isDeleted:
        raise HTTPException(404, "Invoice not found")

    if not reason:
        raise HTTPException(400, "Reason is required for deletion")

    invoice.isDeleted = True
    invoice.deletedBy = current_user.id
    invoice.deletedAt = datetime.utcnow()
    invoice.reason = reason

    db.commit()
    return {"ok": True, "invoiceId": invoice.id}

@app.get("/invoices/next-number")
def get_next_invoice_number(db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT MAX(id) FROM invoices
    """)).scalar()

    next_id = (result or 0) + 1

    invoice_number = f"INV-{next_id:06d}"
    return {"invoiceNumber": invoice_number}

@app.get("/reports/invoices")
def invoice_report(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    include_deleted: bool = Query(False),
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Generate invoice report
    - Filters: from_date, to_date, user_id
    - Include deleted invoices with flag
    """
    query = db.query(Invoice)

    if not include_deleted:
        query = query.filter(Invoice.isDeleted == False)
    
    if from_date:
        query = query.filter(Invoice.createdAt >= from_date)
    if to_date:
        query = query.filter(Invoice.createdAt <= to_date)
    if user_id:
        query = query.filter(Invoice.createdBy == user_id)
    
    invoices = query.order_by(Invoice.createdAt.desc()).all()

    # Aggregate totals
    total_amount = sum(inv.totalAmount for inv in invoices)
    total_tax = sum(inv.tax for inv in invoices)
    total_discount = sum(inv.discount for inv in invoices)
    total_final = sum(inv.finalAmount for inv in invoices)

    # Optional: include invoice items per invoice
    result = []
    for inv in invoices:
        items = [
            {
                "description": i.description,
                "quantity": i.quantity,
                "unitPrice": i.unitPrice,
                "subtotal": i.subtotal
            }
            for i in inv.items
        ]
        result.append({
            "invoice_id": inv.id,
            "booking_id": inv.bookingId,
            "totalAmount": inv.totalAmount,
            "tax": inv.tax,
            "discount": inv.discount,
            "finalAmount": inv.finalAmount,
            "createdBy": inv.createdBy,
            "createdAt": inv.createdAt,
            "updatedBy": inv.updatedBy,
            "updatedAt": inv.updatedAt,
            "reason": inv.reason,
            "isDeleted": inv.isDeleted,
            "items": items,
            "customerName": inv.booking.name if inv.booking else None,
        "mobile": inv.booking.mobile if inv.booking else None,
        "roomNo": inv.booking.roomNo if inv.booking else None,
        "checkInDate": inv.booking.checkInDate if inv.booking else None,
        "checkOutDate": inv.booking.checkOutDate if inv.booking else None,
        "checkInTime": inv.booking.checkInTime if inv.booking else None,
        "checkOutTime": inv.booking.checkOutTime if inv.booking else None,
        "bookingSource": inv.booking.bookingSource if inv.booking else None,
        "paymentMethod": inv.booking.paymentMethod if inv.booking else None,
        "address": inv.booking.address if inv.booking else None,
        "safe": inv.booking.safe if inv.booking else None,
        "bookingNumber": inv.booking.bookingNumber if inv.booking else None,
        "invoiceNumber": inv.invoiceNumber if inv.booking else None,
        "gstNo": inv.booking.customerGstNo if inv.booking else None,
        "numberOfDates": inv.booking.numberOfDates if inv.booking else None,
        "totalNoPeople": inv.booking.totalNoPeople if inv.booking else None,
        "room": inv.booking.room.name if inv.booking and inv.booking.room else None,
        })

    return {
        "count": len(result),
        "totalAmount": total_amount,
        "totalTax": total_tax,
        "totalDiscount": total_discount,
        "totalFinalAmount": total_final,
        "invoices": result
    }

@app.get("/reports/invoices-summary")
def invoice_summary(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Generate invoice summary report for dashboard
    Includes totals per room, per user, per service
    + extended booking details for each invoice
    """
    query = db.query(Invoice)
    if not include_deleted:
        query = query.filter(Invoice.isDeleted == False)
    if from_date:
        query = query.filter(Invoice.createdAt >= from_date)
    if to_date:
        query = query.filter(Invoice.createdAt <= to_date)
    
    invoices = query.order_by(Invoice.createdAt.desc()).all()

    # Totals per room
    room_totals = {}
    for inv in invoices:
        if not inv.booking:
            continue
        room_id = inv.booking.roomId
        if room_id not in room_totals:
            room_totals[room_id] = {
                "roomName": inv.booking.room.name if inv.booking.room else "Unknown",
                "totalAmount": 0.0,
                "totalTax": 0.0,
                "totalDiscount": 0.0,
                "finalAmount": 0.0,
                "invoiceCount": 0
            }
        room_totals[room_id]["totalAmount"] += inv.totalAmount or 0
        room_totals[room_id]["totalTax"] += inv.tax or 0
        room_totals[room_id]["totalDiscount"] += inv.discount or 0
        room_totals[room_id]["finalAmount"] += inv.finalAmount or 0
        room_totals[room_id]["invoiceCount"] += 1

    # Totals per user
    user_totals = {}
    for inv in invoices:
        user_id = inv.createdBy
        if user_id not in user_totals:
            user = db.get(User, user_id)
            user_totals[user_id] = {
                "userName": user.name if user else "Unknown",
                "totalAmount": 0.0,
                "totalTax": 0.0,
                "totalDiscount": 0.0,
                "finalAmount": 0.0,
                "invoiceCount": 0
            }
        user_totals[user_id]["totalAmount"] += inv.totalAmount or 0
        user_totals[user_id]["totalTax"] += inv.tax or 0
        user_totals[user_id]["totalDiscount"] += inv.discount or 0
        user_totals[user_id]["finalAmount"] += inv.finalAmount or 0
        user_totals[user_id]["invoiceCount"] += 1

    # Totals per service
    service_totals = {}
    for inv in invoices:
        for item in inv.items:
            svc_id = item.serviceId
            if svc_id not in service_totals:
                service_totals[svc_id] = {
                    "serviceName": item.description,
                    "quantity": 0,
                    "subtotal": 0.0
                }
            service_totals[svc_id]["quantity"] += item.quantity or 0
            service_totals[svc_id]["subtotal"] += item.subtotal or 0

    # Final response
    return {
        "totalInvoices": len(invoices),
        "roomTotals": list(room_totals.values()),
        "userTotals": list(user_totals.values()),
        "serviceTotals": list(service_totals.values()),
        "invoices": [
            {
                "invoiceId": inv.id,
                "bookingId": inv.bookingId,
                "user": inv.createdBy,
                "room": inv.booking.room.name if inv.booking and inv.booking.room else None,

                # ✅ Extended booking details
                "customerName": inv.booking.name if inv.booking else None,
                "mobile": inv.booking.mobile if inv.booking else None,
                "roomNo": inv.booking.roomNo if inv.booking else None,
                "checkInDate": inv.booking.checkInDate if inv.booking else None,
                "checkOutDate": inv.booking.checkOutDate if inv.booking else None,
                "checkInTime": inv.booking.checkInTime if inv.booking else None,
                "checkOutTime": inv.booking.checkOutTime if inv.booking else None,
                "bookingSource": inv.booking.bookingSource if inv.booking else None,
                "paymentMethod": inv.booking.paymentMethod if inv.booking else None,
                "address": inv.booking.address if inv.booking else None,
                "safe": inv.booking.safe if inv.booking else None,
                "bookingNumber": inv.booking.bookingNumber if inv.booking else None,
                "invoiceNumber": inv.invoiceNumber if inv.booking else None,
                "gstNo": inv.booking.customerGstNo if inv.booking else None,
                "numberOfDates": inv.booking.numberOfDates if inv.booking else None,
                "totalNoPeople": inv.booking.totalNoPeople if inv.booking else None,

                # ✅ Invoice details
                "totalAmount": inv.totalAmount,
                "tax": inv.tax,
                "discount": inv.discount,
                "finalAmount": inv.finalAmount,
                "createdAt": inv.createdAt,
                "updatedAt": inv.updatedAt,
                "reason": inv.reason,
                "isDeleted": inv.isDeleted,

                # ✅ Invoice items
                "items": [
                    {
                        "description": i.description,
                        "quantity": i.quantity,
                        "unitPrice": i.unitPrice,
                        "subtotal": i.subtotal
                    }
                    for i in inv.items
                ]
            }
            for inv in invoices
        ]
    }



@app.post("/admin/services", response_model=ServiceOut)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    # Prevent duplicate service names
    if db.query(Service).filter(Service.name == payload.name).first():
        raise HTTPException(400, "Service with this name already exists")

    s = Service(name=payload.name, price=payload.price)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s



@app.put("/admin/services/{service_id}", response_model=ServiceOut)
def update_service(service_id: int, payload: ServiceCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = db.get(Service, service_id)
    if not s:
        raise HTTPException(404, "Service not found")

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

# plug in accounting routes
app.include_router(accounting_router)

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
        # ---------- Existing table alterations & seeding ----------
        db.execute(text("""ALTER TABLE rooms ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'available';"""))
        db.execute(text("""ALTER TABLE users ADD COLUMN IF NOT EXISTS allowed_features JSON DEFAULT '[]';"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS males INT DEFAULT 0;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS females INT DEFAULT 0;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "documentUrl" VARCHAR;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS name VARCHAR;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS mobile VARCHAR;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "checkInDate" DATE;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "checkInTime" TIME;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "checkOutDate" DATE;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "checkOutTime" TIME;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "customerGstNo" VARCHAR;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "roomNo" VARCHAR;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "numberOfDates" INT DEFAULT 0;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "totalNoPeople" INT DEFAULT 0;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "bookingSource" VARCHAR;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "address" VARCHAR;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "paymentMethod" VARCHAR;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS safe BOOLEAN DEFAULT FALSE;"""))
        db.execute(text("""ALTER TABLE bookings ADD COLUMN IF NOT EXISTS "bookingNumber" VARCHAR;"""))
        db.execute(text("""
                            WITH numbered AS (
                                SELECT id,
                                    ROW_NUMBER() OVER (ORDER BY id) AS rn
                                FROM bookings
                                WHERE "bookingNumber" IS NULL
                            )
                            UPDATE bookings
                            SET "bookingNumber" = CONCAT('BK-', LPAD(numbered.rn::text, 6, '0'))
                            FROM numbered
                            WHERE bookings.id = numbered.id;
                        """))
        db.execute(text("""UPDATE bookings SET "bookingNumber" = 'BK-000002' WHERE "bookingNumber" = 'BK-00002';"""))  
        db.execute(text("""UPDATE bookings SET "bookingNumber" = 'BK-000001' WHERE "bookingNumber" = 'BK-00001';"""))  

        

        # ✅ Add same fields to invoices table       
        # ✅ Add same fields to invoices table
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "customerName" VARCHAR;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS name VARCHAR;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS mobile VARCHAR;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "checkInDate" DATE;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "checkInTime" TIME;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "checkOutDate" DATE;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "checkOutTime" TIME;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "customerGstNo" VARCHAR;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "roomNo" VARCHAR;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "roomName" VARCHAR;"""))  # 🆕 add this
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "gstNo" VARCHAR;""")) 
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "numberOfDates" INT DEFAULT 0;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "totalNoPeople" INT DEFAULT 0;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "bookingSource" VARCHAR;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "paymentMethod" VARCHAR;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "address" VARCHAR;""")) 
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS safe BOOLEAN DEFAULT FALSE;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "bookingNumber" VARCHAR;"""))
        db.execute(text("""ALTER TABLE invoices ADD COLUMN IF NOT EXISTS "invoiceNumber" VARCHAR;"""))
        db.execute(text("""
                        UPDATE invoices
                        SET "invoiceNumber" = CONCAT('INV-', LPAD(id::text, 6, '0'))
                        WHERE "invoiceNumber" IS NULL OR "invoiceNumber" = '';
                        """))

        db.commit()

        # Seed users
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

        # Seed rooms
        if not db.query(Room).count():
            db.add_all([
                Room(name="Deluxe 101", type="Deluxe", price=89.0, description="City view, queen bed", status="available"),
                Room(name="Suite 201", type="Suite", price=159.0, description="King bed, lounge access", status="available"),
            ])

        # Seed services
        if not db.query(Service).count():
            db.add_all([
                Service(name="Breakfast", price=8.0),
                Service(name="Laundry", price=5.0),
                Service(name="Spa", price=35.0),
                Service(name="Cleaning", price=0.0),
            ])
        
        # ---------- Invoice & InvoiceItem table creation ----------
        Base.metadata.create_all(bind=engine, tables=[Invoice.__table__, InvoiceItem.__table__])

        # Optional: Seed a test invoice
        if not db.query(Invoice).count() and db.query(Booking).count():
            booking = db.query(Booking).first()
            invoice_item = InvoiceItem(
                description="Deluxe 101 Room",
                quantity=1,
                unitPrice=booking.room.price,
                subtotal=booking.room.price
            )
            invoice = Invoice(
                bookingId=booking.id,
                totalAmount=booking.room.price,
                tax=booking.room.price * 0.1,      # 10% tax example
                discount=0,
                finalAmount=booking.room.price * 1.1,
                createdBy=booking.userId,
                items=[invoice_item]
            )
            db.add(invoice)

        db.commit()

