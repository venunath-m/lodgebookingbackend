from datetime import datetime
from http.client import HTTPException
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from . import models, schemas
from sqlalchemy import func

router = APIRouter(prefix="/accounting", tags=["Accounting"])


@router.post("/accounts", response_model=schemas.Account)
def create_account(account: schemas.AccountCreate, db: Session = Depends(get_db)):
    db_account = models.Account(name=account.name, account_type=account.account_type)
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


@router.get("/accounts", response_model=list[schemas.Account])
def get_accounts(db: Session = Depends(get_db)):
    return db.query(models.Account).all()


@router.post("/journal_entries", response_model=schemas.JournalEntry)
def create_journal_entry(entry: schemas.JournalEntryCreate, db: Session = Depends(get_db)):
    db_entry = models.JournalEntry(**entry.dict())
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry


@router.get("/journal_entries", response_model=list[schemas.JournalEntry])
def get_journal_entries(db: Session = Depends(get_db)):
    return db.query(models.JournalEntry).all()

@router.get("/trial_balance")
def get_trial_balance(db: Session = Depends(get_db)):
    """
    Generates a trial balance summary showing debit and credit totals per account.
    """
    accounts = db.query(models.Account).all()
    trial_balance = []

    total_debit = 0.0
    total_credit = 0.0

    for account in accounts:
        debit_sum = (
            db.query(models.JournalEntry)
            .filter(models.JournalEntry.account_id == account.id,
                    models.JournalEntry.entry_type == models.EntryType.debit)
            .with_entities(func.coalesce(func.sum(models.JournalEntry.amount), 0.0))
            .scalar()
        )

        credit_sum = (
            db.query(models.JournalEntry)
            .filter(models.JournalEntry.account_id == account.id,
                    models.JournalEntry.entry_type == models.EntryType.credit)
            .with_entities(func.coalesce(func.sum(models.JournalEntry.amount), 0.0))
            .scalar()
        )

        trial_balance.append({
            "account_id": account.id,
            "account_name": account.name,
            "account_type": account.account_type,
            "debit_total": debit_sum,
            "credit_total": credit_sum,
            "net_balance": debit_sum - credit_sum
        })

        total_debit += debit_sum
        total_credit += credit_sum

    return {
        "trial_balance": trial_balance,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": abs(total_debit - total_credit) < 0.001
    }
@router.get("/profit_loss")
def get_profit_and_loss(db: Session = Depends(get_db)):
    """
    Generates a Profit & Loss statement:
    - Totals income and expense accounts
    - Calculates net profit or loss
    """

    income_total = (
        db.query(func.coalesce(func.sum(models.JournalEntry.amount), 0.0))
        .join(models.Account)
        .filter(models.Account.account_type == "income",
                models.JournalEntry.entry_type == models.EntryType.credit)
        .scalar()
    )

    expense_total = (
        db.query(func.coalesce(func.sum(models.JournalEntry.amount), 0.0))
        .join(models.Account)
        .filter(models.Account.account_type == "expense",
                models.JournalEntry.entry_type == models.EntryType.debit)
        .scalar()
    )

    net_profit = income_total - expense_total

    # Optional: breakdown by account
    income_accounts = (
        db.query(models.Account.name, func.sum(models.JournalEntry.amount))
        .join(models.JournalEntry)
        .filter(models.Account.account_type == "income",
                models.JournalEntry.entry_type == models.EntryType.credit)
        .group_by(models.Account.name)
        .all()
    )

    expense_accounts = (
        db.query(models.Account.name, func.sum(models.JournalEntry.amount))
        .join(models.JournalEntry)
        .filter(models.Account.account_type == "expense",
                models.JournalEntry.entry_type == models.EntryType.debit)
        .group_by(models.Account.name)
        .all()
    )

    return {
        "income_total": income_total,
        "expense_total": expense_total,
        "net_profit": net_profit,
        "income_breakdown": [
            {"account_name": name, "amount": total} for name, total in income_accounts
        ],
        "expense_breakdown": [
            {"account_name": name, "amount": total} for name, total in expense_accounts
        ],
        "status": "profit" if net_profit > 0 else "loss" if net_profit < 0 else "break-even"
    }
@router.get("/balance_sheet")
def get_balance_sheet(db: Session = Depends(get_db)):
    """
    Generates a Balance Sheet:
    - Summarizes Assets, Liabilities, and Equity
    - Ensures Assets = Liabilities + Equity
    """

    def get_total_by_type(account_type: str, entry_type: models.EntryType):
        return (
            db.query(func.coalesce(func.sum(models.JournalEntry.amount), 0.0))
            .join(models.Account)
            .filter(models.Account.account_type == account_type,
                    models.JournalEntry.entry_type == entry_type)
            .scalar()
        )

    # --- Assets ---
    asset_debits = get_total_by_type("asset", models.EntryType.debit)
    asset_credits = get_total_by_type("asset", models.EntryType.credit)
    total_assets = asset_debits - asset_credits

    # --- Liabilities ---
    liability_debits = get_total_by_type("liability", models.EntryType.debit)
    liability_credits = get_total_by_type("liability", models.EntryType.credit)
    total_liabilities = liability_credits - liability_debits  # reverse logic for liabilities

    # --- Equity ---
    equity_debits = get_total_by_type("equity", models.EntryType.debit)
    equity_credits = get_total_by_type("equity", models.EntryType.credit)
    total_equity = equity_credits - equity_debits  # normal for capital accounts

    # --- Derived check ---
    is_balanced = abs(total_assets - (total_liabilities + total_equity)) < 0.001

    # Optional: breakdown by account
    asset_accounts = (
        db.query(models.Account.name, func.sum(models.JournalEntry.amount), models.JournalEntry.entry_type)
        .join(models.JournalEntry)
        .filter(models.Account.account_type == "asset")
        .group_by(models.Account.name, models.JournalEntry.entry_type)
        .all()
    )
    liability_accounts = (
        db.query(models.Account.name, func.sum(models.JournalEntry.amount), models.JournalEntry.entry_type)
        .join(models.JournalEntry)
        .filter(models.Account.account_type == "liability")
        .group_by(models.Account.name, models.JournalEntry.entry_type)
        .all()
    )
    equity_accounts = (
        db.query(models.Account.name, func.sum(models.JournalEntry.amount), models.JournalEntry.entry_type)
        .join(models.JournalEntry)
        .filter(models.Account.account_type == "equity")
        .group_by(models.Account.name, models.JournalEntry.entry_type)
        .all()
    )

    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "is_balanced": is_balanced,
        "assets": [
            {"account_name": name, "entry_type": etype.value, "amount": total}
            for name, total, etype in asset_accounts
        ],
        "liabilities": [
            {"account_name": name, "entry_type": etype.value, "amount": total}
            for name, total, etype in liability_accounts
        ],
        "equity": [
            {"account_name": name, "entry_type": etype.value, "amount": total}
            for name, total, etype in equity_accounts
        ]
    }
# 🔹 Year-End Closing Process
@router.post("/year_end")
def close_financial_year(year: int, db: Session = Depends(get_db)):
    """
    Perform year-end closing for the given financial year:
    - Calculate total income and expenses
    - Compute net profit/loss
    - Post to Retained Earnings
    - Lock previous year entries
    """

    # 1️⃣ Fetch all income & expense accounts
    income_accounts = db.query(models.Account).filter(models.Account.account_type == "income").all()
    expense_accounts = db.query(models.Account).filter(models.Account.account_type == "expense").all()

    if not income_accounts and not expense_accounts:
        raise HTTPException(400, "No income or expense accounts found.")

    # 2️⃣ Calculate totals
    total_income = sum(
        e.amount for acc in income_accounts for e in acc.entries if e.entry_type == models.EntryType.credit
    )
    total_expense = sum(
        e.amount for acc in expense_accounts for e in acc.entries if e.entry_type == models.EntryType.debit
    )

    net_profit = total_income - total_expense

    # 3️⃣ Find retained earnings account
    retained_earnings = db.query(models.Account).filter(models.Account.name == "Retained Earnings").first()
    if not retained_earnings:
        raise HTTPException(400, "Retained Earnings account not found. Please create it first.")

    # 4️⃣ Record journal entry
    description = f"Year-end closing for FY {year}"
    if net_profit > 0:
        # Profit → credit retained earnings
        closing_entry = models.JournalEntry(
            account_id=retained_earnings.id,
            entry_type=models.EntryType.credit,
            amount=net_profit,
            description=description
        )
    else:
        # Loss → debit retained earnings
        closing_entry = models.JournalEntry(
            account_id=retained_earnings.id,
            entry_type=models.EntryType.debit,
            amount=abs(net_profit),
            description=description
        )

    db.add(closing_entry)
    db.commit()

    # 5️⃣ Optionally lock the year (can add a “locked_until” table/flag later)
    return {
        "message": f"Year-end process completed for FY {year}",
        "total_income": total_income,
        "total_expense": total_expense,
        "net_profit": net_profit,
    }
@router.get("/yearend/summary")
def get_yearend_summary(db: Session = Depends(get_db)):
    income_total = db.query(func.sum(models.JournalEntry.amount))\
        .join(models.Account)\
        .filter(models.Account.account_type == "income").scalar() or 0

    expense_total = db.query(func.sum(models.JournalEntry.amount))\
        .join(models.Account)\
        .filter(models.Account.account_type == "expense").scalar() or 0

    net_profit = income_total - expense_total

    return {
        "year": datetime.utcnow().year,
        "totalIncome": income_total,
        "totalExpense": expense_total,
        "netProfit": net_profit
    }


@router.post("/yearend/close")
def close_yearend(db: Session = Depends(get_db)):
    # Logic: Transfer net profit/loss to Retained Earnings account
    # and mark entries as closed for the year
    retained_earnings = db.query(models.Account).filter_by(name="Retained Earnings").first()
    if not retained_earnings:
        retained_earnings = models.Account(name="Retained Earnings", account_type="equity")
        db.add(retained_earnings)
        db.commit()
        db.refresh(retained_earnings)

    # Example closing entry
    summary = get_yearend_summary(db)
    entry_type = "credit" if summary["netProfit"] > 0 else "debit"
    amount = abs(summary["netProfit"])

    db_entry = models.JournalEntry(
        account_id=retained_earnings.id,
        entry_type=entry_type,
        amount=amount,
        description=f"Year-end closing for {summary['year']}"
    )
    db.add(db_entry)
    db.commit()

    return {"message": f"Year {summary['year']} closed successfully."}
@router.post("/yearend/reopen")
def reopen_yearend(db: Session = Depends(get_db)):
    """
    Reopen the last closed year-end by deleting or marking the closing entry.
    """
    # Find the most recent closing entry
    last_closing = db.query(models.JournalEntry)\
        .filter(models.JournalEntry.description.like("Year-end closing%"))\
        .order_by(models.JournalEntry.date.desc())\
        .first()

    if not last_closing:
        return {"message": "No closed year found to reopen."}

    # Option 1: delete the closing entry (soft delete)
    last_closing.isReversed = True
    db.commit()

    return {"message": f"Year {datetime.utcnow().year - 1} reopened successfully."}