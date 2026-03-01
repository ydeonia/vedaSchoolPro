"""
Payment API — Sprint 26
Handles all payment operations: create orders, verify payments, webhooks, payment links, refunds.
"""
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.payment import PaymentTransaction, Donation
from models.branch import PaymentGatewayConfig, Branch
from models.fee import FeeRecord, PaymentStatus
from models.student import Student
from utils.payments import get_payment_provider, get_available_gateways

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["Payments"])


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

async def get_branch_gateway_config(branch_id: str, db: AsyncSession):
    """Load payment gateway config for a branch."""
    config = await db.scalar(
        select(PaymentGatewayConfig).where(PaymentGatewayConfig.branch_id == uuid.UUID(branch_id))
    )
    return config


def generate_receipt_number(prefix="RCP"):
    """Generate unique receipt number."""
    ts = datetime.utcnow().strftime("%y%m%d%H%M")
    short = uuid.uuid4().hex[:4].upper()
    return f"{prefix}-{ts}-{short}"


# ═══════════════════════════════════════════════════════════
# GET AVAILABLE GATEWAYS
# ═══════════════════════════════════════════════════════════

@router.get("/gateways/{branch_id}")
async def list_gateways(branch_id: str, db: AsyncSession = Depends(get_db)):
    """Return list of enabled payment gateways for a branch."""
    config = await get_branch_gateway_config(branch_id, db)
    gateways = get_available_gateways(config)
    return {
        "online_enabled": config.online_payments_enabled if config else False,
        "test_mode": config.test_mode if config else False,
        "gateways": gateways,
        "upi": {
            "enabled": config.upi_enabled if config else False,
            "upi_id": config.upi_id if config else None,
            "qr_url": config.upi_qr_url if config else None,
        } if config else {},
        "bank": {
            "enabled": config.bank_transfer_enabled if config else False,
            "bank_name": config.bank_name if config else None,
            "account_number": config.account_number if config else None,
            "ifsc_code": config.ifsc_code if config else None,
            "account_holder": config.account_holder if config else None,
        } if config else {},
    }


# ═══════════════════════════════════════════════════════════
# CREATE ORDER
# ═══════════════════════════════════════════════════════════

@router.post("/create-order")
async def create_order(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create a payment order via selected gateway.
    Body: {branch_id, gateway, amount, purpose, fee_record_id?, student_id?, description?}
    """
    data = await request.json()
    branch_id = data.get("branch_id")
    gateway_name = data.get("gateway", "razorpay")
    amount = float(data.get("amount", 0))
    purpose = data.get("purpose", "fee")
    fee_record_id = data.get("fee_record_id")
    student_id = data.get("student_id")
    description = data.get("description", "")
    callback_url = data.get("callback_url", "")

    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    # Get branch currency
    branch = await db.scalar(select(Branch).where(Branch.id == uuid.UUID(branch_id)))
    currency = branch.currency if branch else "INR"

    # Get gateway config
    config = await get_branch_gateway_config(branch_id, db)
    if not config or not config.online_payments_enabled:
        raise HTTPException(400, "Online payments not enabled for this branch")

    provider = get_payment_provider(config, gateway_name)
    if not provider:
        raise HTTPException(400, f"Gateway '{gateway_name}' not configured or disabled")

    # Create order via gateway
    receipt = generate_receipt_number("ORD")
    try:
        order = await provider.create_order(
            amount=amount,
            currency=currency,
            receipt=receipt,
            notes={
                "branch_id": branch_id,
                "purpose": purpose,
                "student_id": student_id or "",
                "callback_url": callback_url,
                "redirect_url": callback_url,
            }
        )
    except Exception as e:
        logger.error(f"Payment order creation failed: {e}")
        raise HTTPException(500, f"Payment gateway error: {str(e)}")

    # Save transaction
    txn = PaymentTransaction(
        branch_id=uuid.UUID(branch_id),
        student_id=uuid.UUID(student_id) if student_id else None,
        fee_record_id=uuid.UUID(fee_record_id) if fee_record_id else None,
        amount=amount,
        currency=currency,
        gateway=gateway_name,
        gateway_order_id=order["order_id"],
        status="pending",
        purpose=purpose,
        description=description,
        receipt_number=receipt,
        gateway_metadata=order.get("gateway_data", {}),
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)

    return {
        "success": True,
        "transaction_id": str(txn.id),
        "order_id": order["order_id"],
        "amount": amount,
        "currency": currency,
        "gateway": gateway_name,
        "gateway_data": order.get("gateway_data", {}),
    }


# ═══════════════════════════════════════════════════════════
# VERIFY PAYMENT
# ═══════════════════════════════════════════════════════════

@router.post("/verify")
async def verify_payment(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Verify payment after completion (client-side callback).
    Body: {branch_id, gateway, transaction_id, payment_data: {...}}
    """
    data = await request.json()
    branch_id = data.get("branch_id")
    txn_id = data.get("transaction_id")
    payment_data = data.get("payment_data", {})

    # Load transaction
    txn = await db.scalar(select(PaymentTransaction).where(PaymentTransaction.id == uuid.UUID(txn_id)))
    if not txn:
        raise HTTPException(404, "Transaction not found")

    # Get provider
    config = await get_branch_gateway_config(branch_id, db)
    provider = get_payment_provider(config, txn.gateway)
    if not provider:
        raise HTTPException(400, "Gateway not configured")

    # Verify
    try:
        result = await provider.verify_payment(payment_data)
    except Exception as e:
        logger.error(f"Payment verification failed: {e}")
        txn.status = "failed"
        await db.commit()
        return {"success": False, "status": "failed", "error": str(e)}

    if result["verified"]:
        txn.status = "success"
        txn.gateway_payment_id = result.get("payment_id")
        txn.completed_at = datetime.utcnow()
        txn.receipt_number = generate_receipt_number("RCP")

        # Update fee record if linked
        if txn.fee_record_id:
            fee = await db.scalar(select(FeeRecord).where(FeeRecord.id == txn.fee_record_id))
            if fee:
                fee.amount_paid = (fee.amount_paid or 0) + txn.amount
                fee.payment_date = datetime.utcnow().date()
                fee.payment_mode = txn.gateway
                fee.transaction_id = result.get("payment_id", str(txn.id))
                if fee.amount_paid >= fee.amount_due:
                    fee.status = PaymentStatus.PAID
                elif fee.amount_paid > 0:
                    fee.status = PaymentStatus.PARTIAL
    else:
        txn.status = "failed"

    await db.commit()

    return {
        "success": result["verified"],
        "status": txn.status,
        "receipt_number": txn.receipt_number if result["verified"] else None,
        "payment_id": result.get("payment_id"),
    }


# ═══════════════════════════════════════════════════════════
# WEBHOOKS
# ═══════════════════════════════════════════════════════════

@router.post("/webhook/{gateway}")
async def payment_webhook(gateway: str, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Receive webhook from payment gateway.
    Gateway will POST payment status updates here.
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "") or \
                request.headers.get("X-VERIFY", "") or \
                request.headers.get("x-paytm-signature", "")

    try:
        data = await request.json()
    except Exception:
        data = {}

    logger.info(f"Webhook received from {gateway}: {data}")

    # For Razorpay
    if gateway == "razorpay":
        event = data.get("event", "")
        payment = data.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payment.get("order_id")

        if not order_id:
            return {"status": "ignored"}

        txn = await db.scalar(
            select(PaymentTransaction).where(PaymentTransaction.gateway_order_id == order_id)
        )
        if not txn:
            return {"status": "txn_not_found"}

        # Verify webhook signature
        config = await get_branch_gateway_config(str(txn.branch_id), db)
        provider = get_payment_provider(config, "razorpay")
        if provider and not provider.verify_webhook(body, signature):
            logger.warning(f"Invalid webhook signature for order {order_id}")
            raise HTTPException(400, "Invalid signature")

        if event == "payment.captured":
            txn.status = "success"
            txn.gateway_payment_id = payment.get("id")
            txn.completed_at = datetime.utcnow()
            if not txn.receipt_number:
                txn.receipt_number = generate_receipt_number("RCP")

            # Update fee record
            if txn.fee_record_id:
                fee = await db.scalar(select(FeeRecord).where(FeeRecord.id == txn.fee_record_id))
                if fee:
                    fee.amount_paid = (fee.amount_paid or 0) + txn.amount
                    fee.payment_date = datetime.utcnow().date()
                    fee.payment_mode = "razorpay"
                    fee.transaction_id = payment.get("id")
                    fee.status = PaymentStatus.PAID if fee.amount_paid >= fee.amount_due else PaymentStatus.PARTIAL

        elif event == "payment.failed":
            txn.status = "failed"
            txn.gateway_metadata = {**(txn.gateway_metadata or {}), "failure_reason": payment.get("error_description", "")}

        elif "refund" in event:
            refund = data.get("payload", {}).get("refund", {}).get("entity", {})
            txn.refund_id = refund.get("id")
            txn.refund_amount = (refund.get("amount", 0)) / 100
            txn.refund_status = refund.get("status")
            if refund.get("status") == "processed":
                txn.status = "refunded"

        await db.commit()
        return {"status": "ok"}

    # PhonePe webhook
    elif gateway == "phonepe":
        response = data.get("response", "")
        # PhonePe sends base64 encoded response
        # Decode and process
        txn_id = data.get("merchantTransactionId", "")
        if txn_id:
            txn = await db.scalar(
                select(PaymentTransaction).where(PaymentTransaction.gateway_order_id == txn_id)
            )
            if txn:
                code = data.get("code", "")
                if code == "PAYMENT_SUCCESS":
                    txn.status = "success"
                    txn.completed_at = datetime.utcnow()
                    if not txn.receipt_number:
                        txn.receipt_number = generate_receipt_number("RCP")
                else:
                    txn.status = "failed"
                await db.commit()
        return {"status": "ok"}

    return {"status": "unhandled_gateway"}


# ═══════════════════════════════════════════════════════════
# PAYMENT LINKS
# ═══════════════════════════════════════════════════════════

@router.post("/create-link")
async def create_payment_link(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create a payment link and optionally send via WhatsApp/SMS/Email.
    Body: {branch_id, amount, purpose, description, student_id?, fee_record_id?,
           customer: {name, phone, email}, expiry_hours?, send_via?: [whatsapp, sms, email]}
    """
    data = await request.json()
    branch_id = data.get("branch_id")
    amount = float(data.get("amount", 0))
    purpose = data.get("purpose", "fee")
    description = data.get("description", "Payment")
    student_id = data.get("student_id")
    fee_record_id = data.get("fee_record_id")
    customer = data.get("customer", {})
    expiry_hours = data.get("expiry_hours", 72)
    send_via = data.get("send_via", [])
    gateway_name = data.get("gateway", "razorpay")

    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    # Get config
    config = await get_branch_gateway_config(branch_id, db)
    if not config or not config.online_payments_enabled:
        raise HTTPException(400, "Online payments not enabled")

    provider = get_payment_provider(config, gateway_name)
    if not provider:
        raise HTTPException(400, f"Gateway '{gateway_name}' not configured")

    # Get branch for callback URL
    branch = await db.scalar(select(Branch).where(Branch.id == uuid.UUID(branch_id)))
    base_url = branch.website_url or "https://school.eduflow.in"

    try:
        link_result = await provider.create_payment_link(
            amount=amount,
            description=description,
            customer=customer,
            expiry_hours=expiry_hours,
            callback_url=f"{base_url}/payment/success",
        )
    except Exception as e:
        logger.error(f"Payment link creation failed: {e}")
        raise HTTPException(500, f"Failed to create payment link: {str(e)}")

    # Save transaction
    txn = PaymentTransaction(
        branch_id=uuid.UUID(branch_id),
        student_id=uuid.UUID(student_id) if student_id else None,
        fee_record_id=uuid.UUID(fee_record_id) if fee_record_id else None,
        amount=amount,
        currency=branch.currency if branch else "INR",
        gateway=gateway_name,
        gateway_order_id=link_result.get("link_id"),
        status="pending",
        purpose=purpose,
        description=description,
        payment_link=link_result.get("link_url"),
        payment_link_short=link_result.get("short_url"),
        payment_link_id=link_result.get("link_id"),
        link_expiry=datetime.utcnow() + timedelta(hours=expiry_hours),
        payer_name=customer.get("name"),
        payer_phone=customer.get("phone"),
        payer_email=customer.get("email"),
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)

    # TODO: Send via WhatsApp/SMS/Email using notifier.py
    # if "whatsapp" in send_via: await send_whatsapp(...)
    # if "sms" in send_via: await send_sms(...)
    # if "email" in send_via: await send_email(...)

    return {
        "success": True,
        "transaction_id": str(txn.id),
        "link_url": link_result.get("link_url"),
        "short_url": link_result.get("short_url"),
        "link_id": link_result.get("link_id"),
        "expires_at": txn.link_expiry.isoformat() if txn.link_expiry else None,
    }


# ═══════════════════════════════════════════════════════════
# REFUND
# ═══════════════════════════════════════════════════════════

@router.post("/refund")
async def refund_payment(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Initiate a refund.
    Body: {transaction_id, amount? (partial refund), reason?}
    """
    data = await request.json()
    txn_id = data.get("transaction_id")
    amount = data.get("amount")
    reason = data.get("reason", "")

    txn = await db.scalar(select(PaymentTransaction).where(PaymentTransaction.id == uuid.UUID(txn_id)))
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if txn.status != "success":
        raise HTTPException(400, "Can only refund successful transactions")

    config = await get_branch_gateway_config(str(txn.branch_id), db)
    provider = get_payment_provider(config, txn.gateway)
    if not provider:
        raise HTTPException(400, "Gateway not configured")

    try:
        result = await provider.refund(
            payment_id=txn.gateway_payment_id,
            amount=amount or txn.amount,
            reason=reason,
        )
    except Exception as e:
        raise HTTPException(500, f"Refund failed: {str(e)}")

    txn.refund_id = result.get("refund_id")
    txn.refund_amount = result.get("amount", amount or txn.amount)
    txn.refund_status = result.get("status")
    if result.get("status") in ("processed", "success"):
        txn.status = "refunded" if (amount is None or amount >= txn.amount) else "partially_refunded"
    await db.commit()

    return {"success": True, "refund_id": result.get("refund_id"), "status": result.get("status")}


# ═══════════════════════════════════════════════════════════
# TRANSACTIONS LIST
# ═══════════════════════════════════════════════════════════

@router.get("/transactions/{branch_id}")
async def list_transactions(branch_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """List all payment transactions for a branch."""
    status = request.query_params.get("status")
    purpose = request.query_params.get("purpose")
    limit = int(request.query_params.get("limit", 50))
    offset = int(request.query_params.get("offset", 0))

    query = select(PaymentTransaction).where(
        PaymentTransaction.branch_id == uuid.UUID(branch_id)
    ).order_by(PaymentTransaction.created_at.desc())

    if status:
        query = query.where(PaymentTransaction.status == status)
    if purpose:
        query = query.where(PaymentTransaction.purpose == purpose)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    txns = result.scalars().all()

    # Count total
    count_q = select(func.count(PaymentTransaction.id)).where(
        PaymentTransaction.branch_id == uuid.UUID(branch_id)
    )
    total = await db.scalar(count_q) or 0

    return {
        "transactions": [{
            "id": str(t.id),
            "amount": t.amount,
            "currency": t.currency,
            "gateway": t.gateway,
            "status": t.status,
            "purpose": t.purpose,
            "description": t.description,
            "payer_name": t.payer_name,
            "receipt_number": t.receipt_number,
            "payment_link": t.payment_link,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        } for t in txns],
        "total": total,
    }


# ═══════════════════════════════════════════════════════════
# DONATIONS
# ═══════════════════════════════════════════════════════════

@router.post("/donate")
async def create_donation(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create a donation (can be online or offline).
    Body: {branch_id, donor_name, donor_phone?, donor_email?, donor_pan?,
           amount, purpose, student_id?, message?, is_anonymous?, payment_mode}
    """
    data = await request.json()
    branch_id = data.get("branch_id")
    amount = float(data.get("amount", 0))

    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    donation = Donation(
        branch_id=uuid.UUID(branch_id),
        donor_name=data.get("donor_name", "Anonymous"),
        donor_phone=data.get("donor_phone"),
        donor_email=data.get("donor_email"),
        donor_pan=data.get("donor_pan"),
        amount=amount,
        purpose=data.get("purpose", "general"),
        student_id=uuid.UUID(data["student_id"]) if data.get("student_id") else None,
        payment_mode=data.get("payment_mode", "cash"),
        message=data.get("message"),
        is_anonymous=data.get("is_anonymous", False),
        receipt_number=generate_receipt_number("DON"),
        status="completed" if data.get("payment_mode") in ("cash", "cheque", "bank_transfer") else "pending",
    )
    db.add(donation)
    await db.commit()
    await db.refresh(donation)

    return {
        "success": True,
        "donation_id": str(donation.id),
        "receipt_number": donation.receipt_number,
        "status": donation.status,
    }


@router.get("/donations/{branch_id}")
async def list_donations(branch_id: str, db: AsyncSession = Depends(get_db)):
    """List all donations for a branch."""
    result = await db.execute(
        select(Donation).where(Donation.branch_id == uuid.UUID(branch_id))
        .order_by(Donation.created_at.desc()).limit(100)
    )
    donations = result.scalars().all()

    total = sum(d.amount for d in donations if d.status == "completed")

    return {
        "donations": [{
            "id": str(d.id),
            "donor_name": "Anonymous" if d.is_anonymous else d.donor_name,
            "amount": d.amount,
            "purpose": d.purpose,
            "status": d.status,
            "receipt_number": d.receipt_number,
            "payment_mode": d.payment_mode,
            "message": d.message,
            "donor_pan": d.donor_pan,
            "tax_receipt_sent": d.tax_receipt_sent,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        } for d in donations],
        "total_collected": total,
    }


# ═══════════════════════════════════════════════════════════
# PAYMENT LINK INFO (Public — no auth)
# ═══════════════════════════════════════════════════════════

@router.get("/link-info/{link_id}")
async def get_payment_link_info(link_id: str, db: AsyncSession = Depends(get_db)):
    """Public endpoint — returns payment link details for the payment link page."""
    txn = await db.scalar(
        select(PaymentTransaction).where(
            (PaymentTransaction.payment_link_id == link_id) |
            (PaymentTransaction.id == (lambda: uuid.UUID(link_id) if len(link_id) == 36 else None)())
        )
    )
    if not txn:
        return {"success": False, "error": "Link not found"}

    # Check expiry
    if txn.link_expiry and txn.link_expiry < datetime.utcnow():
        return {"success": False, "error": "Link expired"}

    if txn.status == "success":
        return {"success": False, "error": "Already paid"}

    # Get branch info + gateways
    branch = await db.scalar(select(Branch).where(Branch.id == txn.branch_id))
    config = await get_branch_gateway_config(str(txn.branch_id), db)
    gateways = get_available_gateways(config) if config else []

    # Get student name if linked
    student_name = ""
    if txn.student_id:
        student = await db.scalar(select(Student).where(Student.id == txn.student_id))
        if student:
            student_name = f"{student.first_name} {student.last_name}"

    return {
        "success": True,
        "amount": txn.amount,
        "currency": txn.currency,
        "description": txn.description or "Payment",
        "purpose": txn.purpose,
        "branch_id": str(txn.branch_id),
        "school_name": branch.name if branch else "School",
        "student_name": student_name or txn.payer_name,
        "student_id": str(txn.student_id) if txn.student_id else None,
        "fee_record_id": str(txn.fee_record_id) if txn.fee_record_id else None,
        "payer_name": txn.payer_name,
        "gateways": [{"name": g["name"], "label": g["label"]} for g in gateways if g["name"] not in ("upi_direct",)],
    }