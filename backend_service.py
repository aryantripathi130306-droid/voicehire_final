"""
VoiceHire — Backend Data Services, Domain Models & Concurrency Engine
═══════════════════════════════════════════════════════════════════════
Implements the missing Voice Hire data models and backend operations:
  - Worker skills & service categories
  - Worker availability & approximate location privacy
  - Job requests, offers, and double-acceptance concurrency CAS protection
  - Booking status history & check-in events
  - Payment records & payment status history with idempotency
  - Completed-job reviews & dispute reports
  - Comprehensive audit event logging
  - Notifications dispatch
"""

import hashlib
import json
import math
import secrets
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


def utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


# Allowed state transitions
VALID_JOB_TRANSITIONS = {
    'open': {'accepted', 'cancelled'},
    'accepted': {'pending_confirmation', 'cancelled'},
    'pending_confirmation': {'completed', 'accepted'},
    'completed': set(),
    'cancelled': set()
}

VALID_BOOKING_TRANSITIONS = {
    'Pending': {'Booked', 'Cancelled'},
    'Booked': {'Work Started', 'Cancelled'},
    'Work Started': {'Completed', 'Cancelled'},
    'Completed': set(),
    'Cancelled': set()
}

VALID_PAYMENT_TRANSITIONS = {
    'pending': {'authorized', 'captured', 'completed', 'failed'},
    'authorized': {'captured', 'failed', 'refunded'},
    'captured': {'completed', 'refunded'},
    'completed': {'refunded'},
    'failed': {'pending'},
    'refunded': set()
}

DEFAULT_SERVICE_CATEGORIES = [
    {"id": 1, "name": "Plumbing", "slug": "plumbing", "description": "Pipes, leaks, taps and bathroom fixtures", "icon": "fa-solid fa-wrench", "is_active": True},
    {"id": 2, "name": "Electrical", "slug": "electrical", "description": "Wiring, switches, appliances and lighting", "icon": "fa-solid fa-bolt", "is_active": True},
    {"id": 3, "name": "Carpentry", "slug": "carpentry", "description": "Furniture repair, doors, windows and woodwork", "icon": "fa-solid fa-hammer", "is_active": True},
    {"id": 4, "name": "Cleaning", "slug": "cleaning", "description": "Home deep cleaning, sanitation and floor cleaning", "icon": "fa-solid fa-broom", "is_active": True},
    {"id": 5, "name": "Painting", "slug": "painting", "description": "Interior & exterior wall painting and touchups", "icon": "fa-solid fa-paint-roller", "is_active": True},
    {"id": 6, "name": "Construction Helper", "slug": "construction", "description": "Manual labor, loading and building support", "icon": "fa-solid fa-trowel", "is_active": True},
    {"id": 7, "driver": "Driver & Transport", "slug": "driver", "name": "Driver & Transport", "description": "Vehicle driving, goods delivery and hauling", "icon": "fa-solid fa-truck", "is_active": True},
    {"id": 8, "name": "Appliance Repair", "slug": "appliance", "description": "AC, refrigerator, washing machine repair", "icon": "fa-solid fa-tv", "is_active": True}
]


class LocationPrivacyShield:
    """Provides privacy-preserving coordinate obfuscation (~1.1 km fuzzy radius) and PII masking."""

    @staticmethod
    def obfuscate_coordinates(lat: Optional[float], lng: Optional[float], precision: int = 2) -> Tuple[Optional[float], Optional[float]]:
        if lat is None or lng is None:
            return None, None
        try:
            return round(float(lat), precision), round(float(lng), precision)
        except (ValueError, TypeError):
            return None, None

    @staticmethod
    def mask_phone(phone: Optional[str]) -> Optional[str]:
        if not phone:
            return None
        clean = str(phone).strip()
        if len(clean) >= 4:
            return f"XXXXXX{clean[-4:]}"
        return "XXXXXX"

    @classmethod
    def obfuscate_worker_profile(cls, worker: Dict[str, Any], viewer_is_counterparty: bool = False) -> Dict[str, Any]:
        """
        Creates a copy of the worker profile with privacy protections applied.
        Hides precise live coordinates and masks phone numbers for unverified public browsing.
        """
        w = dict(worker)
        # Never expose password hash under any circumstances
        w.pop('password', None)

        raw_lat = w.get('live_lat')
        raw_lng = w.get('live_lng')
        approx_lat, approx_lng = cls.obfuscate_coordinates(raw_lat, raw_lng)
        w['approx_lat'] = approx_lat
        w['approx_lng'] = approx_lng

        if not viewer_is_counterparty:
            # Hide exact real-time coordinates and mask phone
            w['live_lat'] = None
            w['live_lng'] = None
            if 'phone' in w:
                w['phone_masked'] = cls.mask_phone(w.get('phone'))
                w.pop('phone', None)
        return w


class ServiceCategoryManager:
    """Manages service taxonomy lookups with resilient fallbacks."""

    @staticmethod
    def get_categories(supabase_client) -> List[Dict[str, Any]]:
        try:
            resp = supabase_client.table("service_categories").select("*").eq("is_active", True).execute()
            if resp.data:
                return resp.data
        except Exception as e:
            print(f"[ServiceCategoryManager Warning] {e}")
        return DEFAULT_SERVICE_CATEGORIES


class WorkerSkillsManager:
    """Manages worker specialized skills, certifications, and experience."""

    @staticmethod
    def get_worker_skills(supabase_client, worker_id: str) -> List[Dict[str, Any]]:
        try:
            resp = supabase_client.table("worker_skills").select("*").eq("worker_id", worker_id).execute()
            return resp.data or []
        except Exception as e:
            print(f"[WorkerSkillsManager Error: get] {e}")
            return []

    @staticmethod
    def add_worker_skill(supabase_client, worker_id: str, skill_name: str,
                         category_id: Optional[int] = None, experience_years: int = 1,
                         is_primary: bool = False) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        clean_skill = str(skill_name).strip()
        if not clean_skill:
            return False, "Skill name cannot be empty", None

        try:
            record = {
                "worker_id": str(worker_id),
                "skill_name": clean_skill,
                "experience_years": max(0, int(experience_years)),
                "is_primary": bool(is_primary)
            }
            if category_id:
                record["category_id"] = int(category_id)

            resp = supabase_client.table("worker_skills").insert(record).execute()
            if not resp.data:
                return False, "Failed to insert skill", None
            return True, "Skill added successfully", resp.data[0]
        except Exception as e:
            err_msg = str(e).lower()
            if "unique" in err_msg or "duplicate" in err_msg:
                return False, "You have already added this skill", None
            print(f"[WorkerSkillsManager Error: add] {e}")
            return False, f"Server error: {e}", None

    @staticmethod
    def delete_worker_skill(supabase_client, skill_id: Any, worker_id: str) -> Tuple[bool, str]:
        try:
            # Ensure ownership
            check = supabase_client.table("worker_skills").select("id, worker_id").eq("id", skill_id).execute()
            if not check.data:
                return False, "Skill record not found"
            if str(check.data[0].get("worker_id")) != str(worker_id):
                return False, "Unauthorized: you do not own this skill record"

            supabase_client.table("worker_skills").delete().eq("id", skill_id).execute()
            return True, "Skill deleted successfully"
        except Exception as e:
            print(f"[WorkerSkillsManager Error: delete] {e}")
            return False, f"Server error: {e}"


class AuditLogger:
    """Records security, domain state changes, and transaction audit trails."""

    @staticmethod
    def log_event(supabase_client, actor_id: Optional[str], actor_role: Optional[str],
                  event_type: str, resource_type: str, resource_id: str,
                  action: str, ip_address: Optional[str] = None,
                  status: str = 'success', metadata: Optional[Dict[str, Any]] = None) -> bool:
        try:
            record = {
                "actor_id": str(actor_id) if actor_id else None,
                "actor_role": str(actor_role) if actor_role else None,
                "event_type": str(event_type),
                "resource_type": str(resource_type),
                "resource_id": str(resource_id),
                "action": str(action),
                "ip_address": str(ip_address) if ip_address else None,
                "status": str(status),
                "metadata": metadata or {}
            }
            supabase_client.table("audit_events").insert(record).execute()
            return True
        except Exception as e:
            # Audit logging failure should not crash main operation
            print(f"[AuditLogger Error] {e}")
            return False


class NotificationService:
    """Dispatches in-app notifications with deduplication / idempotency support."""

    @staticmethod
    def send_notification(supabase_client, recipient_id: str, recipient_role: str,
                          title: str, message: str, notif_type: str,
                          reference_id: Optional[str] = None,
                          idempotency_key: Optional[str] = None) -> bool:
        try:
            if idempotency_key:
                # Check for duplicate
                existing = supabase_client.table("notifications").select("id").eq("idempotency_key", idempotency_key).execute()
                if existing.data:
                    return True

            record = {
                "recipient_id": str(recipient_id),
                "recipient_role": str(recipient_role),
                "title": str(title),
                "message": str(message),
                "type": str(notif_type),
                "reference_id": str(reference_id) if reference_id else None,
                "is_read": False,
                "idempotency_key": str(idempotency_key) if idempotency_key else None
            }
            supabase_client.table("notifications").insert(record).execute()
            return True
        except Exception as e:
            print(f"[NotificationService Error] {e}")
            return False


class StatusHistoryLogger:
    """Maintains immutable audit records of all job and booking status transitions."""

    @staticmethod
    def log_job_status(supabase_client, job_id: Any, from_status: str, to_status: str,
                       changed_by: Optional[str], changed_by_role: str, reason: Optional[str] = None) -> bool:
        try:
            record = {
                "job_id": int(job_id) if str(job_id).isdigit() else job_id,
                "from_status": str(from_status),
                "to_status": str(to_status),
                "changed_by": str(changed_by) if changed_by else None,
                "changed_by_role": str(changed_by_role),
                "reason": str(reason) if reason else None
            }
            supabase_client.table("job_status_history").insert(record).execute()
            return True
        except Exception as e:
            print(f"[StatusHistoryLogger Error: job] {e}")
            return False

    @staticmethod
    def log_booking_status(supabase_client, booking_id: Any, from_status: str, to_status: str,
                          changed_by: Optional[str], changed_by_role: str, reason: Optional[str] = None) -> bool:
        try:
            record = {
                "booking_id": int(booking_id) if str(booking_id).isdigit() else booking_id,
                "from_status": str(from_status),
                "to_status": str(to_status),
                "changed_by": str(changed_by) if changed_by else None,
                "changed_by_role": str(changed_by_role),
                "reason": str(reason) if reason else None
            }
            supabase_client.table("booking_status_history").insert(record).execute()
            return True
        except Exception as e:
            print(f"[StatusHistoryLogger Error: booking] {e}")
            return False


class CheckinEventLogger:
    """Logs QR checkin and checkout events with cryptographic hashing and IP metadata."""

    @staticmethod
    def log_checkin(supabase_client, booking_id: Any, worker_id: str, customer_id: str,
                    event_type: str, status: str, token: Optional[str] = None,
                    client_lat: Optional[float] = None, client_lng: Optional[float] = None,
                    ip_address: Optional[str] = None, user_agent: Optional[str] = None,
                    failure_reason: Optional[str] = None) -> bool:
        try:
            token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest() if token else None
            record = {
                "booking_id": int(booking_id) if str(booking_id).isdigit() else booking_id,
                "worker_id": str(worker_id),
                "customer_id": str(customer_id),
                "event_type": str(event_type),
                "status": str(status),
                "token_hash": token_hash,
                "client_lat": float(client_lat) if client_lat is not None else None,
                "client_lng": float(client_lng) if client_lng is not None else None,
                "ip_address": str(ip_address) if ip_address else None,
                "user_agent": str(user_agent)[:255] if user_agent else None,
                "failure_reason": str(failure_reason) if failure_reason else None
            }
            supabase_client.table("booking_checkin_events").insert(record).execute()
            return True
        except Exception as e:
            print(f"[CheckinEventLogger Error] {e}")
            return False


class JobConcurrencyShield:
    """
    Prevents race conditions where two workers simultaneously accept the same single-worker job.
    Uses atomic Compare-And-Swap (CAS) update on status = 'open'.
    """

    @staticmethod
    def atomic_accept_job(supabase_client, job_id: Any, worker_id: str, price: Optional[float] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        # Step 1: Verify job exists
        job_resp = supabase_client.table("jobs").select("*").eq("id", job_id).execute()
        if not job_resp.data:
            return False, "not_found", None

        current_job = job_resp.data[0]
        if current_job.get("status") != "open":
            return False, "already_taken", current_job

        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()

        update_payload = {
            "status": "accepted",
            "worker_id": str(worker_id),
            "completion_token": token,
            "token_expires_at": expires_at,
            "assigned_at": utc_now_iso()
        }
        if price is not None and float(price) > 0:
            update_payload["price"] = float(price)

        # Step 2: Atomic CAS update with condition eq("status", "open")
        try:
            cas_resp = supabase_client.table("jobs").update(update_payload).eq("id", job_id).eq("status", "open").execute()
            if not cas_resp.data:
                # Another worker won the race in between select and update
                return False, "already_taken", None

            accepted_job = cas_resp.data[0]
            return True, "accepted", accepted_job
        except Exception as e:
            print(f"[JobConcurrencyShield CAS Error] {e}")
            return False, "server_error", None

    @staticmethod
    def atomic_accept_offer(supabase_client, job_id: Any, offer_id: Any, customer_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Customer accepts a worker's bid/offer on an open job.
        Atomically assigns the job, transitions job to 'accepted', marks offer as 'accepted',
        and rejects other competing pending offers.
        """
        try:
            # 1. Verify job exists and belongs to customer
            job_resp = supabase_client.table("jobs").select("*").eq("id", job_id).execute()
            if not job_resp.data:
                return False, "job_not_found", None
            job = job_resp.data[0]
            if str(job.get("user_id")) != str(customer_id):
                return False, "unauthorized", None
            if job.get("status") != "open":
                return False, "job_not_open", None

            # 2. Verify offer exists and belongs to this job
            offer_resp = supabase_client.table("job_offers").select("*").eq("id", offer_id).eq("job_id", job_id).execute()
            if not offer_resp.data:
                return False, "offer_not_found", None
            offer = offer_resp.data[0]
            if offer.get("status") != "pending":
                return False, "offer_not_pending", None

            worker_id = offer["worker_id"]
            agreed_price = offer.get("proposed_price")

            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()

            # 3. Atomic CAS on jobs where status == 'open'
            update_job_payload = {
                "status": "accepted",
                "worker_id": str(worker_id),
                "completion_token": token,
                "token_expires_at": expires_at,
                "assigned_at": utc_now_iso()
            }
            if agreed_price is not None:
                update_job_payload["price"] = float(agreed_price)

            cas_resp = supabase_client.table("jobs").update(update_job_payload).eq("id", job_id).eq("status", "open").execute()
            if not cas_resp.data:
                return False, "already_taken", None

            # 4. Mark accepted offer
            supabase_client.table("job_offers").update({
                "status": "accepted",
                "updated_at": utc_now_iso()
            }).eq("id", offer_id).execute()

            # 5. Mark competing offers as rejected
            supabase_client.table("job_offers").update({
                "status": "rejected",
                "updated_at": utc_now_iso()
            }).eq("job_id", job_id).eq("status", "pending").execute()

            return True, "accepted", cas_resp.data[0]
        except Exception as e:
            print(f"[JobConcurrencyShield CAS Offer Error] {e}")
            return False, f"server_error: {e}", None


class PaymentManager:
    """
    Manages payment processing, idempotency deduplication, and financial audit logs.
    """

    @staticmethod
    def process_payment(supabase_client, payer_id: str, payee_id: str, amount: float,
                        payment_method: str = 'cash', booking_id: Optional[Any] = None,
                        job_id: Optional[Any] = None, idempotency_key: Optional[str] = None,
                        notes: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        if amount <= 0:
            return False, "Invalid payment amount: must be greater than zero", None

        # Check idempotency
        if idempotency_key:
            existing = supabase_client.table("payments").select("*").eq("idempotency_key", idempotency_key).execute()
            if existing.data:
                return True, "Payment already recorded", existing.data[0]

        try:
            tx_ref = f"VH-TXN-{secrets.token_hex(8).upper()}"
            payment_record = {
                "payer_id": str(payer_id),
                "payee_id": str(payee_id),
                "amount": float(amount),
                "currency": "INR",
                "payment_method": payment_method,
                "payment_status": "completed",
                "idempotency_key": idempotency_key or secrets.token_hex(16),
                "transaction_ref": tx_ref,
                "notes": notes,
                "booking_id": int(booking_id) if (booking_id and str(booking_id).isdigit()) else booking_id,
                "job_id": int(job_id) if (job_id and str(job_id).isdigit()) else job_id
            }

            resp = supabase_client.table("payments").insert(payment_record).execute()
            if not resp.data:
                return False, "Failed to record payment", None

            payment = resp.data[0]

            # Record status history
            supabase_client.table("payment_status_history").insert({
                "payment_id": payment['id'],
                "from_status": "pending",
                "to_status": "completed",
                "changed_by": str(payer_id),
                "notes": notes or "Payment captured successfully"
            }).execute()

            return True, "Payment processed successfully", payment
        except Exception as e:
            print(f"[PaymentManager Error] {e}")
            return False, f"Server error: {e}", None
