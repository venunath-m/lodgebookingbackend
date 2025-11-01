from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class EntryType(str, Enum):
    debit = "debit"
    credit = "credit"


class AccountBase(BaseModel):
    name: str
    account_type: str


class AccountCreate(AccountBase):
    pass


class Account(AccountBase):
    id: int

    class Config:
        orm_mode = True


class JournalEntryBase(BaseModel):
    account_id: int
    entry_type: EntryType
    amount: float
    description: str | None = None


class JournalEntryCreate(JournalEntryBase):
    pass


class JournalEntry(JournalEntryBase):
    id: int
    date: datetime

    class Config:
        orm_mode = True
