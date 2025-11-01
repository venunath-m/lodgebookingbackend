from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean ,ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import enum


class EntryType(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    account_type = Column(String, nullable=False)  # asset, liability, income, expense, etc.

    entries = relationship("JournalEntry", back_populates="account")


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    entry_type = Column(Enum(EntryType), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String)
    date = Column(DateTime, default=datetime.utcnow)
    isReversed = Column(Boolean, default=False)

    account = relationship("Account", back_populates="entries")
