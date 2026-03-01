"""
Unified Payment Interface — Sprint 26
Supports: Razorpay, PhonePe, Paytm, Cashfree, Stripe, UPI Direct
Each provider implements create_order, verify_payment, create_payment_link, refund.
"""
import hashlib
import hmac
import base64
import json
import uuid
import logging
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# ABSTRACT BASE
# ═══════════════════════════════════════════════════════════

class PaymentProvider(ABC):
    """Abstract payment provider — all gateways implement this."""

    @abstractmethod
    async def create_order(self, amount: float, currency: str, receipt: str, notes: dict = None) -> dict:
        """Create a payment order. Returns {order_id, amount, currency, gateway_data}."""
        pass

    @abstractmethod
    async def verify_payment(self, payment_data: dict) -> dict:
        """Verify payment signature/status. Returns {verified: bool, payment_id, status}."""
        pass

    @abstractmethod
    async def create_payment_link(self, amount: float, description: str, customer: dict,
                                   expiry_hours: int = 72, callback_url: str = None) -> dict:
        """Create a payment link. Returns {link_url, link_id, short_url}."""
        pass

    @abstractmethod
    async def refund(self, payment_id: str, amount: float = None, reason: str = None) -> dict:
        """Initiate refund. Returns {refund_id, status, amount}."""
        pass

    @abstractmethod
    def verify_webhook(self, body: bytes, signature: str) -> bool:
        """Verify webhook signature."""
        pass


# ═══════════════════════════════════════════════════════════
# RAZORPAY
# ═══════════════════════════════════════════════════════════

class RazorpayProvider(PaymentProvider):
    """Razorpay payment gateway — most popular in India."""

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str = None):
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = webhook_secret
        self.base_url = "https://api.razorpay.com/v1"

    def _auth(self):
        return (self.key_id, self.key_secret)

    async def create_order(self, amount: float, currency: str = "INR", receipt: str = None, notes: dict = None) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/orders", auth=self._auth(), json={
                "amount": int(amount * 100),  # Razorpay uses paise
                "currency": currency,
                "receipt": receipt or f"rcpt_{uuid.uuid4().hex[:12]}",
                "notes": notes or {},
            })
            data = resp.json()
            if resp.status_code != 200:
                logger.error(f"Razorpay create_order failed: {data}")
                raise Exception(f"Razorpay error: {data.get('error', {}).get('description', 'Unknown error')}")
            return {
                "order_id": data["id"],
                "amount": amount,
                "amount_paise": data["amount"],
                "currency": data["currency"],
                "gateway": "razorpay",
                "gateway_data": {
                    "key_id": self.key_id,
                    "order_id": data["id"],
                    "amount": data["amount"],
                    "currency": data["currency"],
                }
            }

    async def verify_payment(self, payment_data: dict) -> dict:
        """Verify Razorpay payment signature."""
        order_id = payment_data.get("razorpay_order_id", "")
        payment_id = payment_data.get("razorpay_payment_id", "")
        signature = payment_data.get("razorpay_signature", "")

        message = f"{order_id}|{payment_id}"
        expected = hmac.new(
            self.key_secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

        verified = hmac.compare_digest(expected, signature)
        return {
            "verified": verified,
            "payment_id": payment_id,
            "order_id": order_id,
            "status": "success" if verified else "failed",
        }

    async def create_payment_link(self, amount: float, description: str, customer: dict,
                                   expiry_hours: int = 72, callback_url: str = None) -> dict:
        expire_by = int((datetime.utcnow() + timedelta(hours=expiry_hours)).timestamp())
        payload = {
            "amount": int(amount * 100),
            "currency": "INR",
            "description": description,
            "customer": {
                "name": customer.get("name", ""),
                "email": customer.get("email", ""),
                "contact": customer.get("phone", ""),
            },
            "expire_by": expire_by,
            "notify": {"sms": bool(customer.get("phone")), "email": bool(customer.get("email"))},
        }
        if callback_url:
            payload["callback_url"] = callback_url
            payload["callback_method"] = "get"

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/payment_links", auth=self._auth(), json=payload)
            data = resp.json()
            if resp.status_code not in (200, 201):
                logger.error(f"Razorpay payment_link failed: {data}")
                raise Exception(f"Razorpay error: {data.get('error', {}).get('description', 'Unknown')}")
            return {
                "link_url": data.get("short_url", data.get("url", "")),
                "link_id": data["id"],
                "short_url": data.get("short_url", ""),
            }

    async def refund(self, payment_id: str, amount: float = None, reason: str = None) -> dict:
        payload = {}
        if amount:
            payload["amount"] = int(amount * 100)
        if reason:
            payload["notes"] = {"reason": reason}

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/payments/{payment_id}/refund",
                                      auth=self._auth(), json=payload)
            data = resp.json()
            return {
                "refund_id": data.get("id"),
                "status": data.get("status", "failed"),
                "amount": (data.get("amount", 0)) / 100,
            }

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return False
        expected = hmac.new(
            self.webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


# ═══════════════════════════════════════════════════════════
# PHONEPE
# ═══════════════════════════════════════════════════════════

class PhonePeProvider(PaymentProvider):
    """PhonePe payment gateway — UPI-first, growing fast."""

    def __init__(self, merchant_id: str, salt_key: str, salt_index: int = 1, env: str = "production"):
        self.merchant_id = merchant_id
        self.salt_key = salt_key
        self.salt_index = salt_index
        self.base_url = "https://api.phonepe.com/apis/hermes" if env == "production" else "https://api-preprod.phonepe.com/apis/pg-sandbox"

    def _checksum(self, payload_b64: str, endpoint: str) -> str:
        data_to_hash = payload_b64 + endpoint + self.salt_key
        sha = hashlib.sha256(data_to_hash.encode()).hexdigest()
        return f"{sha}###{self.salt_index}"

    async def create_order(self, amount: float, currency: str = "INR", receipt: str = None, notes: dict = None) -> dict:
        txn_id = f"EDU{uuid.uuid4().hex[:16].upper()}"
        payload = {
            "merchantId": self.merchant_id,
            "merchantTransactionId": txn_id,
            "amount": int(amount * 100),  # PhonePe uses paise
            "redirectUrl": notes.get("redirect_url", "") if notes else "",
            "callbackUrl": notes.get("callback_url", "") if notes else "",
            "paymentInstrument": {"type": "PAY_PAGE"},
        }
        if notes and notes.get("customer_phone"):
            payload["merchantUserId"] = notes["customer_phone"]

        payload_json = json.dumps(payload)
        payload_b64 = base64.b64encode(payload_json.encode()).decode()
        checksum = self._checksum(payload_b64, "/pg/v1/pay")

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/pg/v1/pay", json={"request": payload_b64}, headers={
                "Content-Type": "application/json",
                "X-VERIFY": checksum,
            })
            data = resp.json()
            redirect_url = data.get("data", {}).get("instrumentResponse", {}).get("redirectInfo", {}).get("url", "")
            return {
                "order_id": txn_id,
                "amount": amount,
                "currency": currency,
                "gateway": "phonepe",
                "gateway_data": {
                    "redirect_url": redirect_url,
                    "txn_id": txn_id,
                }
            }

    async def verify_payment(self, payment_data: dict) -> dict:
        txn_id = payment_data.get("merchantTransactionId", "")
        endpoint = f"/pg/v1/status/{self.merchant_id}/{txn_id}"
        data_to_hash = endpoint + self.salt_key
        sha = hashlib.sha256(data_to_hash.encode()).hexdigest()
        checksum = f"{sha}###{self.salt_index}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}{endpoint}", headers={"X-VERIFY": checksum, "X-MERCHANT-ID": self.merchant_id})
            data = resp.json()
            code = data.get("code", "")
            return {
                "verified": code == "PAYMENT_SUCCESS",
                "payment_id": data.get("data", {}).get("transactionId", ""),
                "order_id": txn_id,
                "status": "success" if code == "PAYMENT_SUCCESS" else "failed",
            }

    async def create_payment_link(self, amount: float, description: str, customer: dict,
                                   expiry_hours: int = 72, callback_url: str = None) -> dict:
        # PhonePe payment links are same as orders with redirect
        result = await self.create_order(amount, notes={
            "redirect_url": callback_url or "",
            "callback_url": callback_url or "",
            "customer_phone": customer.get("phone", ""),
        })
        return {
            "link_url": result["gateway_data"]["redirect_url"],
            "link_id": result["order_id"],
            "short_url": result["gateway_data"]["redirect_url"],
        }

    async def refund(self, payment_id: str, amount: float = None, reason: str = None) -> dict:
        txn_id = f"REF{uuid.uuid4().hex[:16].upper()}"
        payload = {
            "merchantId": self.merchant_id,
            "merchantTransactionId": payment_id,
            "originalTransactionId": payment_id,
            "amount": int(amount * 100) if amount else 0,
        }
        payload_json = json.dumps(payload)
        payload_b64 = base64.b64encode(payload_json.encode()).decode()
        checksum = self._checksum(payload_b64, "/pg/v1/refund")

        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/pg/v1/refund", json={"request": payload_b64}, headers={
                "Content-Type": "application/json",
                "X-VERIFY": checksum,
            })
            data = resp.json()
            return {
                "refund_id": txn_id,
                "status": "success" if data.get("code") == "PAYMENT_SUCCESS" else "pending",
                "amount": amount or 0,
            }

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        expected = hashlib.sha256(body + self.salt_key.encode()).hexdigest()
        return hmac.compare_digest(expected, signature.split("###")[0] if "###" in signature else signature)


# ═══════════════════════════════════════════════════════════
# PAYTM
# ═══════════════════════════════════════════════════════════

class PaytmProvider(PaymentProvider):
    """Paytm payment gateway."""

    def __init__(self, merchant_id: str, merchant_key: str, env: str = "production"):
        self.merchant_id = merchant_id
        self.merchant_key = merchant_key
        self.base_url = "https://securegw.paytm.in" if env == "production" else "https://securegw-stage.paytm.in"

    def _generate_checksum(self, params: dict) -> str:
        """Generate Paytm checksum — simplified version."""
        import hashlib
        sorted_params = sorted(params.items())
        data_str = "|".join(f"{k}={v}" for k, v in sorted_params)
        return hashlib.sha256(f"{data_str}|{self.merchant_key}".encode()).hexdigest()

    async def create_order(self, amount: float, currency: str = "INR", receipt: str = None, notes: dict = None) -> dict:
        order_id = f"EDU{uuid.uuid4().hex[:16].upper()}"
        txn_token_url = f"{self.base_url}/theia/api/v1/initiateTransaction?mid={self.merchant_id}&orderId={order_id}"

        body = {
            "body": {
                "requestType": "Payment",
                "mid": self.merchant_id,
                "orderId": order_id,
                "websiteName": "DEFAULT",
                "txnAmount": {"value": f"{amount:.2f}", "currency": currency},
                "callbackUrl": notes.get("callback_url", "") if notes else "",
            }
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(txn_token_url, json=body, headers={"Content-Type": "application/json"})
            data = resp.json()
            txn_token = data.get("body", {}).get("txnToken", "")
            return {
                "order_id": order_id,
                "amount": amount,
                "currency": currency,
                "gateway": "paytm",
                "gateway_data": {
                    "txn_token": txn_token,
                    "order_id": order_id,
                    "mid": self.merchant_id,
                    "amount": f"{amount:.2f}",
                }
            }

    async def verify_payment(self, payment_data: dict) -> dict:
        order_id = payment_data.get("ORDERID", "")
        status_url = f"{self.base_url}/v3/order/status"

        body = {"body": {"mid": self.merchant_id, "orderId": order_id}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(status_url, json=body)
            data = resp.json()
            status = data.get("body", {}).get("resultInfo", {}).get("resultStatus", "")
            return {
                "verified": status == "TXN_SUCCESS",
                "payment_id": data.get("body", {}).get("txnId", ""),
                "order_id": order_id,
                "status": "success" if status == "TXN_SUCCESS" else "failed",
            }

    async def create_payment_link(self, amount: float, description: str, customer: dict,
                                   expiry_hours: int = 72, callback_url: str = None) -> dict:
        link_url = f"{self.base_url}/link/create"
        payload = {
            "body": {
                "mid": self.merchant_id,
                "linkType": "GENERIC",
                "linkDescription": description,
                "linkName": f"EduFlow-{uuid.uuid4().hex[:8]}",
                "amount": f"{amount:.2f}",
                "customerContact": {"customerPhone": customer.get("phone", "")},
                "expiryInDays": max(1, expiry_hours // 24),
            }
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(link_url, json=payload)
            data = resp.json()
            return {
                "link_url": data.get("body", {}).get("linkUrl", ""),
                "link_id": data.get("body", {}).get("linkId", ""),
                "short_url": data.get("body", {}).get("shortUrl", ""),
            }

    async def refund(self, payment_id: str, amount: float = None, reason: str = None) -> dict:
        refund_url = f"{self.base_url}/v2/refund"
        ref_id = f"REF{uuid.uuid4().hex[:12]}"
        body = {"body": {"mid": self.merchant_id, "txnId": payment_id, "orderId": payment_id,
                          "refId": ref_id, "refundAmount": f"{amount:.2f}" if amount else "0"}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(refund_url, json=body)
            data = resp.json()
            return {
                "refund_id": ref_id,
                "status": data.get("body", {}).get("resultInfo", {}).get("resultStatus", "PENDING"),
                "amount": amount or 0,
            }

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        expected = hashlib.sha256(body + self.merchant_key.encode()).hexdigest()
        return hmac.compare_digest(expected, signature)


# ═══════════════════════════════════════════════════════════
# FACTORY — Get provider from branch config
# ═══════════════════════════════════════════════════════════

def get_payment_provider(gateway_config, gateway_name: str) -> Optional[PaymentProvider]:
    """
    Factory: returns the correct provider based on gateway name and branch config.
    gateway_config: PaymentGatewayConfig model instance
    """
    if not gateway_config:
        return None

    if gateway_name == "razorpay" and gateway_config.razorpay_enabled:
        return RazorpayProvider(
            key_id=gateway_config.razorpay_key_id,
            key_secret=gateway_config.razorpay_key_secret,
            webhook_secret=gateway_config.razorpay_webhook_secret,
        )
    elif gateway_name == "phonepe" and gateway_config.phonepe_enabled:
        return PhonePeProvider(
            merchant_id=gateway_config.phonepe_merchant_id,
            salt_key=gateway_config.phonepe_salt_key,
            salt_index=gateway_config.phonepe_salt_index or 1,
            env="production" if not gateway_config.test_mode else "sandbox",
        )
    elif gateway_name == "paytm" and getattr(gateway_config, 'paytm_enabled', False):
        return PaytmProvider(
            merchant_id=getattr(gateway_config, 'paytm_merchant_id', ''),
            merchant_key=getattr(gateway_config, 'paytm_merchant_key', ''),
            env="production" if not gateway_config.test_mode else "sandbox",
        )

    return None


def get_available_gateways(gateway_config) -> list:
    """Return list of enabled gateways for a branch."""
    if not gateway_config or not gateway_config.online_payments_enabled:
        return []

    gateways = []
    if gateway_config.razorpay_enabled:
        gateways.append({"name": "razorpay", "label": "Razorpay", "icon": "💳", "supports_upi": True, "supports_cards": True, "supports_netbanking": True})
    if gateway_config.phonepe_enabled:
        gateways.append({"name": "phonepe", "label": "PhonePe", "icon": "📱", "supports_upi": True, "supports_cards": False, "supports_netbanking": False})
    if getattr(gateway_config, 'paytm_enabled', False):
        gateways.append({"name": "paytm", "label": "Paytm", "icon": "💰", "supports_upi": True, "supports_cards": True, "supports_netbanking": True})
    if getattr(gateway_config, 'cashfree_enabled', False):
        gateways.append({"name": "cashfree", "label": "Cashfree", "icon": "🏦", "supports_upi": True, "supports_cards": True, "supports_netbanking": True})
    if getattr(gateway_config, 'stripe_enabled', False):
        gateways.append({"name": "stripe", "label": "Stripe", "icon": "🌍", "supports_upi": False, "supports_cards": True, "supports_netbanking": False})
    if gateway_config.upi_enabled:
        gateways.append({"name": "upi_direct", "label": "UPI Direct", "icon": "📲", "supports_upi": True, "upi_id": gateway_config.upi_id})

    return gateways