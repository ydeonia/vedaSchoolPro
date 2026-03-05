"""
Unified Notification Engine — Sprint 26
Dispatches notifications to: in_app, WhatsApp, SMS, Email, TathaAstu.
Uses branch-specific config from CommunicationConfig.
"""
import logging
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# MAIN DISPATCHER
# ═══════════════════════════════════════════════════════════

async def send_notification(
    db,
    branch_id: str,
    user_id: str = None,
    notification_type: str = "message",
    title: str = "",
    message: str = "",
    channels: List[str] = None,
    data: Dict[str, Any] = None,
    recipient_phone: str = None,
    recipient_email: str = None,
    action_url: str = None,
    action_label: str = None,
    priority: str = "normal",
):
    """
    Send notification through multiple channels.
    
    channels: ["in_app", "whatsapp", "sms", "email", "tathaastu"]
    If not specified, uses branch notification preferences for the type.
    """
    from models.notification import Notification, NotificationChannel
    from models.payment import NotificationLog
    from models.branch import CommunicationConfig
    from sqlalchemy import select
    import uuid

    if channels is None:
        channels = ["in_app"]

    results = {}
    data = data or {}

    # Get branch communication config
    comm_config = await db.scalar(
        select(CommunicationConfig).where(CommunicationConfig.branch_id == uuid.UUID(branch_id))
    )

    # 1. IN-APP — always save to notifications table
    if "in_app" in channels:
        notif = Notification(
            branch_id=uuid.UUID(branch_id),
            user_id=uuid.UUID(user_id) if user_id else None,
            type=notification_type,
            title=title,
            message=message,
            channel=NotificationChannel.IN_APP,
            priority=priority,
            action_url=action_url,
            action_label=action_label,
        )
        db.add(notif)
        results["in_app"] = {"status": "sent"}

    # 2. WHATSAPP
    if "whatsapp" in channels and recipient_phone:
        try:
            wa_result = await send_whatsapp(comm_config, recipient_phone, title, message, data)
            log = NotificationLog(
                branch_id=uuid.UUID(branch_id),
                channel="whatsapp",
                provider=wa_result.get("provider", "interakt"),
                recipient=recipient_phone,
                status=wa_result.get("status", "sent"),
                provider_message_id=wa_result.get("message_id"),
            )
            db.add(log)
            results["whatsapp"] = wa_result
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            log = NotificationLog(
                branch_id=uuid.UUID(branch_id), channel="whatsapp",
                recipient=recipient_phone, status="failed", error_message=str(e),
            )
            db.add(log)
            results["whatsapp"] = {"status": "failed", "error": str(e)}

    # 3. SMS — use PlatformConfig override if available, else branch config
    if "sms" in channels and recipient_phone:
        try:
            sms_config = await get_sms_config(db, branch_id) or comm_config
            sms_result = await send_sms(sms_config, recipient_phone, message, data)
            log = NotificationLog(
                branch_id=uuid.UUID(branch_id),
                channel="sms",
                provider=sms_result.get("provider", "msg91"),
                recipient=recipient_phone,
                status=sms_result.get("status", "sent"),
                provider_message_id=sms_result.get("message_id"),
                cost=sms_result.get("cost", 0),
            )
            db.add(log)
            results["sms"] = sms_result
        except Exception as e:
            logger.error(f"SMS send failed: {e}")
            log = NotificationLog(
                branch_id=uuid.UUID(branch_id), channel="sms",
                recipient=recipient_phone, status="failed", error_message=str(e),
            )
            db.add(log)
            results["sms"] = {"status": "failed", "error": str(e)}

    # 4. EMAIL
    if "email" in channels and recipient_email:
        try:
            email_result = await send_email(comm_config, recipient_email, title, message, data)
            log = NotificationLog(
                branch_id=uuid.UUID(branch_id),
                channel="email",
                provider=email_result.get("provider", "brevo"),
                recipient=recipient_email,
                status=email_result.get("status", "sent"),
                provider_message_id=email_result.get("message_id"),
            )
            db.add(log)
            results["email"] = email_result
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            log = NotificationLog(
                branch_id=uuid.UUID(branch_id), channel="email",
                recipient=recipient_email, status="failed", error_message=str(e),
            )
            db.add(log)
            results["email"] = {"status": "failed", "error": str(e)}

    # 5. TATHAASTU (via Firebase push)
    if "tathaastu" in channels:
        try:
            ta_result = await send_tathaastu_push(comm_config, user_id, title, message, data)
            results["tathaastu"] = ta_result
        except Exception as e:
            logger.error(f"TathaAstu push failed: {e}")
            results["tathaastu"] = {"status": "failed", "error": str(e)}

    await db.commit()
    return results


# ═══════════════════════════════════════════════════════════
# WHATSAPP — Interakt / Wati / Direct Meta API
# ═══════════════════════════════════════════════════════════

async def send_whatsapp(comm_config, phone: str, title: str, message: str, data: dict = None) -> dict:
    """Send WhatsApp message via configured provider."""
    if not comm_config or not comm_config.whatsapp_enabled:
        return {"status": "skipped", "reason": "WhatsApp not enabled"}

    # Normalize phone: ensure country code
    phone = normalize_phone(phone)

    # Use Interakt API (most common in India for WhatsApp Business)
    api_token = comm_config.whatsapp_api_token
    phone_id = comm_config.whatsapp_phone_id

    if not api_token:
        return {"status": "skipped", "reason": "No API token configured"}

    # Try Interakt-style API
    headers = {
        "Authorization": f"Basic {api_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "countryCode": "+91",
        "phoneNumber": phone.replace("+91", "").replace("+", ""),
        "callbackData": json.dumps(data or {}),
        "type": "Text",
        "data": {
            "message": f"*{title}*\n\n{message}",
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.interakt.ai/v1/public/message/",
                headers=headers,
                json=payload,
            )
            result = resp.json()
            return {
                "status": "sent" if resp.status_code in (200, 201) else "failed",
                "provider": "interakt",
                "message_id": result.get("id", ""),
                "response": result,
            }
    except Exception as e:
        # Fallback: try direct WhatsApp Cloud API
        return await _send_whatsapp_cloud_api(api_token, phone_id, phone, title, message)


async def _send_whatsapp_cloud_api(token: str, phone_id: str, phone: str, title: str, message: str) -> dict:
    """Direct WhatsApp Cloud API (Meta)."""
    if not phone_id:
        return {"status": "failed", "reason": "No phone_id for Cloud API"}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": f"*{title}*\n\n{message}"},
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://graph.facebook.com/v17.0/{phone_id}/messages",
            headers=headers, json=payload,
        )
        result = resp.json()
        msg_id = result.get("messages", [{}])[0].get("id", "") if result.get("messages") else ""
        return {
            "status": "sent" if resp.status_code == 200 else "failed",
            "provider": "meta_cloud",
            "message_id": msg_id,
        }


# ═══════════════════════════════════════════════════════════
# SMS — MSG91 / Twilio / Textlocal
# ═══════════════════════════════════════════════════════════

async def send_sms(comm_config, phone: str, message: str, data: dict = None, sms_type: str = "transactional") -> dict:
    """
    Send SMS via configured provider.
    sms_type: "otp" → forces OTP route (MsgClub route 8)
              "transactional" → uses transactional route (MsgClub route 1)
              "promotional" → uses promotional route (MsgClub route 2)
    """
    if not comm_config or not comm_config.sms_enabled:
        return {"status": "skipped", "reason": "SMS not enabled"}

    phone = normalize_phone(phone)
    provider = (comm_config.sms_provider or "msg91").lower()
    api_key = comm_config.sms_api_key

    if not api_key:
        return {"status": "skipped", "reason": "No SMS API key"}

    if provider == "msg91":
        return await _send_sms_msg91(api_key, comm_config.sms_sender_id, phone, message)
    elif provider == "twilio":
        return await _send_sms_twilio(api_key, phone, message)
    elif provider == "textlocal":
        return await _send_sms_textlocal(api_key, comm_config.sms_sender_id, phone, message)
    elif provider == "msgclub":
        # Route selection: OTP=8, Transactional=1, Promotional=2
        if sms_type == "otp":
            route_id = "8"
        elif sms_type == "promotional":
            route_id = "2"
        else:
            route_id = getattr(comm_config, 'sms_route_id', None) or "1"
        return await _send_sms_msgclub(api_key, comm_config.sms_sender_id, phone, message, route_id)
    else:
        return {"status": "failed", "reason": f"Unknown SMS provider: {provider}"}


async def _send_sms_msg91(api_key: str, sender_id: str, phone: str, message: str) -> dict:
    """Send SMS via MSG91."""
    headers = {"authkey": api_key, "Content-Type": "application/json"}
    payload = {
        "flow_id": "",  # Use flow-based for DLT compliance
        "sender": sender_id or "EDUFLW",
        "mobiles": phone.replace("+", ""),
        "message": message,
    }

    # MSG91 Send SMS API
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://control.msg91.com/api/v5/flow/",
            headers=headers, json=payload,
        )
        result = resp.json() if resp.status_code == 200 else {}
        return {
            "status": "sent" if resp.status_code == 200 else "failed",
            "provider": "msg91",
            "message_id": result.get("request_id", ""),
            "cost": 0.25,  # Approximate INR per SMS
        }


async def _send_sms_twilio(api_key: str, phone: str, message: str) -> dict:
    """Send SMS via Twilio."""
    # api_key format: "ACCOUNT_SID:AUTH_TOKEN:FROM_NUMBER"
    parts = api_key.split(":")
    if len(parts) < 3:
        return {"status": "failed", "reason": "Invalid Twilio config (need SID:TOKEN:FROM)"}

    sid, token, from_number = parts[0], parts[1], parts[2]

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"To": phone, "From": from_number, "Body": message},
        )
        result = resp.json() if resp.status_code in (200, 201) else {}
        return {
            "status": "sent" if resp.status_code in (200, 201) else "failed",
            "provider": "twilio",
            "message_id": result.get("sid", ""),
            "cost": 0.50,
        }


async def _send_sms_textlocal(api_key: str, sender: str, phone: str, message: str) -> dict:
    """Send SMS via Textlocal."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.textlocal.in/send/",
            data={
                "apikey": api_key,
                "sender": sender or "EDUFLW",
                "numbers": phone.replace("+91", "").replace("+", ""),
                "message": message,
            },
        )
        result = resp.json() if resp.status_code == 200 else {}
        return {
            "status": "sent" if result.get("status") == "success" else "failed",
            "provider": "textlocal",
            "message_id": str(result.get("batch_id", "")),
            "cost": result.get("cost", 0.25),
        }


async def _send_sms_msgclub(api_key: str, sender_id: str, phone: str, message: str, route_id: str = "8") -> dict:
    """
    Send SMS via MsgClub (msg.msgclub.net).
    route_id: 1=Transactional, 2=Promotional, 8=OTP, etc.
    """
    # Strip country code for msgclub — they expect 10-digit Indian numbers
    mobile = phone.replace("+91", "").replace("+", "").replace(" ", "")
    if mobile.startswith("91") and len(mobile) == 12:
        mobile = mobile[2:]

    params = {
        "AUTH_KEY": api_key,
        "message": message,
        "senderId": sender_id or "EDUFLW",
        "routeId": route_id,
        "mobileNos": mobile,
        "smsContentType": "english",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "http://msg.msgclub.net/rest/services/sendSMS/sendGroupSms",
                params=params,
            )
            result = resp.json() if resp.status_code == 200 else {}
            success = result.get("responseCode") == "3001"
            if not success:
                logger.warning(
                    f"MsgClub SMS response: code={result.get('responseCode')}, "
                    f"msg={result.get('response', '')}, senderId={sender_id}, "
                    f"mobile={mobile}, http={resp.status_code}"
                )
            else:
                logger.info(f"MsgClub SMS sent OK: mobile={mobile}, senderId={sender_id}")
            return {
                "status": "sent" if success else "failed",
                "reason": f"MsgClub code {result.get('responseCode')}: {result.get('response', '')}" if not success else "",
                "provider": "msgclub",
                "message_id": result.get("response", ""),
                "response_code": result.get("responseCode", ""),
                "cost": 0.20,
            }
    except Exception as e:
        logger.error(f"MsgClub SMS failed: {e}")
        return {"status": "failed", "provider": "msgclub", "error": str(e)}


# ═══════════════════════════════════════════════════════════
# EMAIL — Brevo / SES / SMTP
# ═══════════════════════════════════════════════════════════

async def send_platform_email(db, to_email: str, subject: str, body_html: str) -> dict:
    """
    Send email using PlatformConfig SMTP settings (Super Admin level).
    Falls back to any branch CommunicationConfig with email enabled.
    """
    from sqlalchemy import select
    from models.branch import PlatformConfig, CommunicationConfig

    # 1. Try PlatformConfig SMTP
    try:
        platform = await db.scalar(select(PlatformConfig))
        if platform and platform.config:
            pc = platform.config
            if pc.get("smtp_host") and pc.get("smtp_username"):
                return await _send_email_smtp(
                    host=pc["smtp_host"],
                    port=int(pc.get("smtp_port", 587)),
                    username=pc["smtp_username"],
                    password=pc.get("smtp_password", ""),
                    from_email=pc.get("from_email", pc["smtp_username"]),
                    to_email=to_email,
                    subject=subject,
                    body=body_html,
                )
    except Exception as e:
        logger.warning(f"PlatformConfig email failed: {e}")

    # 2. Fallback to any CommunicationConfig
    try:
        comm = await db.scalar(
            select(CommunicationConfig).where(CommunicationConfig.email_enabled == True)
        )
        if comm:
            return await send_email(comm, to_email, subject, body_html)
    except Exception:
        pass

    return {"status": "skipped", "reason": "No email provider configured. Set SMTP in Settings → Email."}


async def send_email(comm_config, to_email: str, subject: str, body: str, data: dict = None) -> dict:
    """Send email via configured provider."""
    if not comm_config or not comm_config.email_enabled:
        return {"status": "skipped", "reason": "Email not enabled"}

    # Use SMTP if configured
    smtp_host = comm_config.smtp_host
    if smtp_host:
        return await _send_email_smtp(
            host=smtp_host,
            port=comm_config.smtp_port or 587,
            username=comm_config.smtp_username,
            password=comm_config.smtp_password,
            from_email=comm_config.from_email,
            to_email=to_email,
            subject=subject,
            body=body,
        )

    return {"status": "skipped", "reason": "No email provider configured"}


async def _send_email_smtp(host: str, port: int, username: str, password: str,
                            from_email: str, to_email: str, subject: str, body: str) -> dict:
    """Send email via SMTP (works with Brevo, Gmail, SES SMTP, etc.)."""
    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject

        # Plain text
        msg.attach(MIMEText(body, "plain"))
        # HTML version
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
            <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:20px;border-radius:12px 12px 0 0;">
                <h2 style="color:white;margin:0;">{subject}</h2>
            </div>
            <div style="background:#ffffff;padding:20px;border:1px solid #e2e8f0;border-radius:0 0 12px 12px;">
                <p style="color:#334155;line-height:1.6;">{body}</p>
            </div>
            <p style="color:#94a3b8;font-size:12px;text-align:center;margin-top:16px;">
                Powered by EduFlow School Management System
            </p>
        </div>
        """
        msg.attach(MIMEText(html, "html"))

        await aiosmtplib.send(
            msg,
            hostname=host,
            port=port,
            username=username,
            password=password,
            use_tls=port == 465,
            start_tls=port == 587,
        )
        return {"status": "sent", "provider": "smtp", "message_id": ""}
    except Exception as e:
        logger.error(f"SMTP email failed: {e}")
        return {"status": "failed", "provider": "smtp", "error": str(e)}


# ═══════════════════════════════════════════════════════════
# TATHAASTU — Firebase Push Notification
# ═══════════════════════════════════════════════════════════

async def send_tathaastu_push(comm_config, user_id: str, title: str, message: str, data: dict = None) -> dict:
    """Send push notification to TathaAstu app via Firebase FCM."""
    if not comm_config or not comm_config.tathaastu_enabled:
        return {"status": "skipped", "reason": "TathaAstu not enabled"}

    # TathaAstu integration would use FCM token stored per user
    # For now, return placeholder
    return {"status": "queued", "provider": "tathaastu_fcm", "note": "FCM integration pending"}


# ═══════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════

def normalize_phone(phone: str) -> str:
    """Normalize phone number to +91XXXXXXXXXX format."""
    if not phone:
        return ""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = phone[1:]
    if not phone.startswith("+"):
        if phone.startswith("91") and len(phone) == 12:
            phone = "+" + phone
        else:
            phone = "+91" + phone
    return phone


async def get_sms_config(db, branch_id: str = None):
    """
    Resolve SMS configuration with correct priority:
      1. PlatformConfig (Super Admin level — platform-wide master override)
      2. Branch-specific CommunicationConfig
      3. Any CommunicationConfig with SMS enabled (fallback)

    Returns a config object with: sms_enabled, sms_provider, sms_api_key,
    sms_sender_id, sms_route_id — or None if no SMS config found.
    """
    from sqlalchemy import select
    from models.branch import PlatformConfig, CommunicationConfig

    # 1. PlatformConfig — Super Admin platform-wide settings (HIGHEST priority)
    try:
        platform = await db.scalar(select(PlatformConfig))
        if platform and platform.config:
            pc = platform.config
            if pc.get("sms_provider") and pc.get("sms_api_key"):
                from types import SimpleNamespace
                return SimpleNamespace(
                    sms_enabled=True,
                    sms_provider=pc["sms_provider"],
                    sms_api_key=pc["sms_api_key"],
                    sms_sender_id=pc.get("sms_sender_id", "EDUFLW"),
                    sms_route_id=pc.get("sms_route_id", "8"),
                )
    except Exception as e:
        logger.warning(f"PlatformConfig SMS lookup failed: {e}")

    # 2. Branch-specific CommunicationConfig
    import uuid as _uuid
    if branch_id:
        try:
            comm = await db.scalar(
                select(CommunicationConfig).where(
                    CommunicationConfig.branch_id == _uuid.UUID(branch_id),
                    CommunicationConfig.sms_enabled == True,
                )
            )
            if comm:
                return comm
        except Exception:
            pass

    # 3. Any CommunicationConfig with SMS enabled (last-resort fallback)
    try:
        comm = await db.scalar(
            select(CommunicationConfig).where(CommunicationConfig.sms_enabled == True)
        )
        if comm:
            return comm
    except Exception:
        pass

    return None


# ═══════════════════════════════════════════════════════════
# CONVENIENCE — Auto-trigger helpers
# ═══════════════════════════════════════════════════════════

async def notify_fee_reminder(db, branch_id: str, student_id: str, parent_phone: str,
                                parent_email: str, student_name: str, amount: float, due_date: str):
    """Send fee reminder to parent."""
    title = "Fee Reminder"
    message = f"Dear Parent, a fee of ₹{amount:,.0f} for {student_name} is due on {due_date}. Please pay on time to avoid late fees."

    return await send_notification(
        db, branch_id, channels=["in_app", "whatsapp", "sms"],
        notification_type="fee_reminder", title=title, message=message,
        recipient_phone=parent_phone, recipient_email=parent_email,
        action_url="/parent/fees", action_label="Pay Now",
    )


async def notify_attendance_absent(db, branch_id: str, parent_phone: str,
                                     student_name: str, date_str: str):
    """Notify parent about student absence."""
    title = "Attendance Alert"
    message = f"Dear Parent, {student_name} was marked absent on {date_str}. If this is incorrect, please contact the school."

    return await send_notification(
        db, branch_id, channels=["in_app", "whatsapp"],
        notification_type="attendance", title=title, message=message,
        recipient_phone=parent_phone,
    )


async def notify_payment_received(db, branch_id: str, parent_phone: str, parent_email: str,
                                    student_name: str, amount: float, receipt_no: str):
    """Notify parent about successful payment."""
    title = "Payment Received ✅"
    message = f"Thank you! Payment of ₹{amount:,.0f} received for {student_name}. Receipt: {receipt_no}."

    return await send_notification(
        db, branch_id, channels=["in_app", "whatsapp", "sms"],
        notification_type="fee_received", title=title, message=message,
        recipient_phone=parent_phone, recipient_email=parent_email,
    )


async def notify_result_published(db, branch_id: str, parent_phone: str, parent_email: str,
                                    student_name: str, exam_name: str):
    """Notify parent when result is published."""
    title = "Result Published 📋"
    message = f"Results for {exam_name} have been published for {student_name}. Login to view the detailed report card."

    return await send_notification(
        db, branch_id, channels=["in_app", "whatsapp", "email"],
        notification_type="result_published", title=title, message=message,
        recipient_phone=parent_phone, recipient_email=parent_email,
        action_url="/parent/results", action_label="View Results",
    )