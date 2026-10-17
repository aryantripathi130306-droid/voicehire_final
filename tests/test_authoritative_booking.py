"""
VoiceHire — Automated Test Suite for Authoritative Booking Workflow
═══════════════════════════════════════════════════════════════════════════
Validates:
  1. Full authoritative lifecycle progression:
     Pending ➔ Booked ➔ On The Way ➔ Arrived ➔ Work Started (QR Check-in) ➔ Completed ➔ Paid
  2. Rejection of impossible and invalid state transitions (e.g. Pending ➔ Completed, Cancelled ➔ Booked)
  3. Rejection of unauthorized mutations and views (non-participants, customer attempting worker actions)
  4. Concurrency protection against competing worker acceptance and repeated API calls (CAS integrity)
  5. Stage-by-stage cancellation policies (Pending, Booked, Travelling, Arrived)
  6. Strict cancellation policy for work already started (Work Started requires >=10 chars explanation)
  7. Stage-based PII privacy protection (contact numbers and exact addresses masked during Pending)
  8. Safe in-app coordination messaging and phone sanitization during unconfirmed stages
  9. Dispute filing and counterparty notifications
 10. AI Chatbot / Voice Assistant booking status guidance and anti-manufacture security guard
"""

import json
import unittest
from unittest.mock import patch

from app import app, make_qr_token
from backend_service import (
    BookingWorkflowManager,
    VALID_BOOKING_TRANSITIONS,
    LocationPrivacyShield,
)
from orchestration_engine import orchestration_engine, ConversationState, AssistantAction


class MockTableQuery:
    """In-memory PostgREST query builder for isolated booking workflow unit tests."""
    def __init__(self, data=None):
        self._data = data if data is not None else []
        self._filters = {}
        self._or_expr = None
        self._selected_cols = "*"
        self._last_inserted = None
        self._pending_updates = None
        self._pending_delete = False
        self._order_col = None
        self._desc = False
        self._limit = None

    def select(self, cols="*"):
        self._selected_cols = cols
        return self

    def insert(self, record):
        if isinstance(record, dict):
            new_rec = dict(record)
            if 'id' not in new_rec:
                new_rec['id'] = len(self._data) + 1
            self._data.append(new_rec)
            self._last_inserted = [dict(new_rec)]
        elif isinstance(record, list):
            self._last_inserted = []
            for r in record:
                nr = dict(r)
                if 'id' not in nr:
                    nr['id'] = len(self._data) + 1
                self._data.append(nr)
                self._last_inserted.append(dict(nr))
        return self

    def update(self, updates):
        self._pending_updates = dict(updates)
        return self

    def delete(self):
        self._pending_delete = True
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def neq(self, col, val):
        self._filters[f"{col}__neq"] = val
        return self

    def in_(self, col, vals):
        self._filters[f"{col}__in"] = set(vals)
        return self

    def ilike(self, col, pattern):
        self._filters[f"{col}__ilike"] = pattern.replace('%', '').lower()
        return self

    def or_(self, or_expr):
        self._or_expr = or_expr
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._desc = desc
        return self

    def limit(self, count):
        self._limit = count
        return self

    def execute(self):
        if self._last_inserted is not None:
            res = list(self._last_inserted)
            self._last_inserted = None
            return MockTableResponse(res)

        matching = []
        for rec in self._data:
            match = True
            for k, v in self._filters.items():
                if k.endswith("__neq"):
                    col = k[:-5]
                    if rec.get(col) == v:
                        match = False
                        break
                elif k.endswith("__in"):
                    col = k[:-4]
                    if rec.get(col) not in v:
                        match = False
                        break
                elif k.endswith("__ilike"):
                    col = k[:-7]
                    if v not in str(rec.get(col, '')).lower():
                        match = False
                        break
                else:
                    if str(rec.get(k)) != str(v):
                        match = False
                        break
            if match:
                matching.append(rec)

        if self._or_expr:
            or_conditions = []
            for part in self._or_expr.split(','):
                subparts = part.strip().split('.eq.')
                if len(subparts) == 2:
                    or_conditions.append((subparts[0], subparts[1]))
            if or_conditions:
                matching = [
                    rec for rec in matching
                    if any(str(rec.get(col)) == str(val) for col, val in or_conditions)
                ]

        if self._pending_delete:
            self._pending_delete = False
            for rec in list(matching):
                if rec in self._data:
                    self._data.remove(rec)
            return MockTableResponse([dict(r) for r in matching])

        if self._pending_updates is not None:
            updated = []
            for rec in matching:
                rec.update(self._pending_updates)
                updated.append(dict(rec))
            self._pending_updates = None
            return MockTableResponse(updated)

        if self._order_col:
            matching.sort(key=lambda r: str(r.get(self._order_col, '')), reverse=self._desc)

        res = [dict(r) for r in matching]
        if self._limit is not None:
            res = res[:self._limit]
        return MockTableResponse(res)


class MockTableResponse:
    def __init__(self, data):
        self.data = data


class MockDatabase:
    """Mock Supabase client providing isolated in-memory tables."""
    def __init__(self):
        self.tables = {
            "users": [],
            "workers": [],
            "jobs": [],
            "bookings": [],
            "booking_status_history": [],
            "booking_checkin_events": [],
            "booking_messages": [],
            "notifications": [],
            "reports": [],
            "audit_events": [],
            "payments": []
        }

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = []
        return MockTableQuery(self.tables[table_name])


class TestAuthoritativeBookingWorkflow(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.mock_db = MockDatabase()
        self.patcher = patch('app.supabase', self.mock_db)
        self.patcher.start()

        # Seed standard users
        self.customer = {
            "id": "cust-101",
            "name": "Amit Sharma",
            "phone": "9876543210",
            "email": "amit@example.com",
            "profile_pic": "uploads/amit.jpg"
        }
        self.worker1 = {
            "id": "wrk-201",
            "name": "Rajesh Kumar",
            "phone": "9123456789",
            "work": "Plumber",
            "price": 500,
            "profile_pic": "uploads/rajesh.jpg"
        }
        self.worker2 = {
            "id": "wrk-202",
            "name": "Sunil Verma",
            "phone": "9988776655",
            "work": "Plumber",
            "price": 450,
            "profile_pic": "uploads/sunil.jpg"
        }
        self.other_user = {
            "id": "cust-999",
            "name": "Intruder User",
            "phone": "9000000000"
        }

        self.mock_db.table("users").insert(self.customer).execute()
        self.mock_db.table("users").insert(self.other_user).execute()
        self.mock_db.table("workers").insert(self.worker1).execute()
        self.mock_db.table("workers").insert(self.worker2).execute()

    def tearDown(self):
        self.patcher.stop()

    def _create_booking(self, status="Pending", customer_id="cust-101", worker_id="wrk-201"):
        """Helper to insert a test booking."""
        booking = {
            "id": 1,
            "customer_id": customer_id,
            "worker_id": worker_id,
            "status": status,
            "date": "2026-10-20",
            "time_slot": "10:00 AM - 12:00 PM",
            "total_price": 500,
            "location": "Flat 402, Sunshine Heights, Sector 62, Noida",
            "qr_token": "valid-token-hex-123456",
            "created_at": "2026-10-15T09:00:00Z"
        }
        resp = self.mock_db.table("bookings").insert(booking).execute()
        return resp.data[0]

    # ─────────────────────────────────────────────────────────────────
    # 1. Full Authoritative Lifecycle Progression
    # ─────────────────────────────────────────────────────────────────
    def test_full_authoritative_lifecycle_progression(self):
        """
        Validates complete valid progression:
        Pending ➔ Booked ➔ On The Way ➔ Arrived ➔ Work Started ➔ Completed ➔ Paid
        """
        b = self._create_booking(status="Pending")
        booking_id = b['id']

        # Step 1: Worker accepts booking (Pending ➔ Booked)
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-201"
            sess['role'] = "worker"
            sess['name'] = "Rajesh Kumar"

        res = self.client.post(f"/api/bookings/{booking_id}/accept")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'Booked')

        # Check notification delivered to customer
        notifs = self.mock_db.table("notifications").select("*").eq("recipient_id", "cust-101").execute().data
        self.assertTrue(any("accepted" in n['title'].lower() for n in notifs))

        # Step 2: Worker starts travelling (Booked ➔ On The Way)
        res = self.client.post(f"/api/bookings/{booking_id}/travel", json={"eta_minutes": 25})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'On The Way')

        # Step 3: Worker arrives at location (On The Way ➔ Arrived)
        res = self.client.post(f"/api/bookings/{booking_id}/arrive")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'Arrived')

        # Step 4: Worker verifies QR code check-in (Arrived ➔ Work Started)
        # Generate valid HMAC token
        token = make_qr_token(booking_id)
        res = self.client.post(f"/api/bookings/{booking_id}/checkin", json={
            "token": token,
            "lat": 28.6139,
            "lng": 77.2090
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'Work Started')

        # Verify check-in audit event was logged
        checkin_events = self.mock_db.table("booking_checkin_events").select("*").eq("booking_id", booking_id).execute().data
        self.assertTrue(len(checkin_events) >= 1)
        self.assertEqual(checkin_events[-1]['status'], 'success')

        # Step 5: Customer marks work complete (Work Started ➔ Completed)
        with self.client.session_transaction() as sess:
            sess['user_id'] = "cust-101"
            sess['role'] = "user"
            sess['name'] = "Amit Sharma"

        res = self.client.post(f"/api/bookings/{booking_id}/complete")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'Completed')

        # Step 6: Direct settlement to Paid
        success, msg, updated = BookingWorkflowManager.transition_status(
            self.mock_db, booking_id, "Paid", "cust-101", "user", reason="Direct cash settlement"
        )
        self.assertTrue(success)
        self.assertEqual(updated['status'], 'Paid')

        # Verify full chronological status history
        history = self.mock_db.table("booking_status_history").select("*").eq("booking_id", booking_id).execute().data
        self.assertEqual(len(history), 6)
        statuses = [h['new_status'] for h in history]
        self.assertEqual(statuses, ['Booked', 'On The Way', 'Arrived', 'Work Started', 'Completed', 'Paid'])

    # ─────────────────────────────────────────────────────────────────
    # 2. Rejection of Impossible and Stale Transitions
    # ─────────────────────────────────────────────────────────────────
    def test_impossible_transitions_rejected(self):
        """Validates that impossible or out-of-order transitions are rejected with 400."""
        b = self._create_booking(status="Pending")
        booking_id = b['id']

        # Worker session
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-201"
            sess['role'] = "worker"

        # Impossible: Pending ➔ Completed directly
        res = self.client.post(f"/api/bookings/{booking_id}/complete")
        self.assertEqual(res.status_code, 400)
        err = res.get_json()['error'].lower()
        self.assertTrue("cannot" in err or "impossible" in err)

        # Impossible: Pending ➔ Arrived directly
        res = self.client.post(f"/api/bookings/{booking_id}/arrive")
        self.assertEqual(res.status_code, 400)

        # Accept booking ➔ Booked
        self.client.post(f"/api/bookings/{booking_id}/accept")

        # Impossible: Booked ➔ Paid directly
        success, msg, _ = BookingWorkflowManager.transition_status(
            self.mock_db, booking_id, "Paid", "wrk-201", "worker"
        )
        self.assertFalse(success)
        self.assertIn("impossible", msg.lower())

        # Cancel booking ➔ Cancelled (Terminal)
        self.client.post(f"/api/bookings/{booking_id}/cancel", json={"reason": "Customer requested cancel"})
        current = self.mock_db.table("bookings").select("*").eq("id", booking_id).execute().data[0]
        self.assertEqual(current['status'], 'Cancelled')

        # Impossible: Cancelled ➔ Booked or Work Started
        success, msg, _ = BookingWorkflowManager.transition_status(
            self.mock_db, booking_id, "Booked", "wrk-201", "worker"
        )
        self.assertFalse(success)
        self.assertIn("impossible", msg.lower())

    # ─────────────────────────────────────────────────────────────────
    # 3. Authorization Violations Guard
    # ─────────────────────────────────────────────────────────────────
    def test_authorization_violations_rejected(self):
        """Ensures non-participants and mismatched roles cannot view or alter bookings."""
        b = self._create_booking(status="Pending")
        booking_id = b['id']

        # Case 1: Unauthenticated user gets 401
        res = self.client.get(f"/api/bookings/{booking_id}")
        self.assertEqual(res.status_code, 401)

        # Case 2: Non-participant (cust-999) viewing gets 403
        with self.client.session_transaction() as sess:
            sess['user_id'] = "cust-999"
            sess['role'] = "user"
        res = self.client.get(f"/api/bookings/{booking_id}")
        self.assertEqual(res.status_code, 403)

        # Case 3: Non-participant trying to accept gets 401 (not worker role) or 403
        res = self.client.post(f"/api/bookings/{booking_id}/accept")
        self.assertEqual(res.status_code, 401)

        # Case 4: Customer trying to trigger worker travel gets 401
        with self.client.session_transaction() as sess:
            sess['user_id'] = "cust-101"
            sess['role'] = "user"
        res = self.client.post(f"/api/bookings/{booking_id}/travel")
        self.assertEqual(res.status_code, 401)

        # Case 5: Different worker (wrk-202) trying to accept booking assigned to wrk-201 gets 403
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-202"
            sess['role'] = "worker"
        res = self.client.post(f"/api/bookings/{booking_id}/accept")
        self.assertEqual(res.status_code, 403)

    # ─────────────────────────────────────────────────────────────────
    # 4. Competing Worker Acceptance & Repeated API Calls
    # ─────────────────────────────────────────────────────────────────
    def test_competing_acceptance_and_repeated_calls(self):
        """Verifies Compare-And-Swap (CAS) shield prevents duplicate/competing acceptance."""
        b = self._create_booking(status="Pending")
        booking_id = b['id']

        # Worker 1 accepts
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-201"
            sess['role'] = "worker"
        res1 = self.client.post(f"/api/bookings/{booking_id}/accept")
        self.assertEqual(res1.status_code, 200)

        # Repeated call by Worker 1 should fail cleanly (already Booked)
        res_repeat = self.client.post(f"/api/bookings/{booking_id}/accept")
        err = res_repeat.get_json()['error'].lower()
        self.assertTrue("already" in err or "not pending" in err)

        # Worker 2 attempting to accept now should be rejected
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-202"
            sess['role'] = "worker"
        res_competing = self.client.post(f"/api/bookings/{booking_id}/accept")
        self.assertIn(res_competing.status_code, [400, 403, 409])

    # ─────────────────────────────────────────────────────────────────
    # 5. Cancellation at Each Relevant Stage
    # ─────────────────────────────────────────────────────────────────
    def test_cancellations_at_each_stage(self):
        """Tests that bookings can be cancelled at Pending, Booked, On The Way, and Arrived."""
        stages = ["Pending", "Booked", "On The Way", "Arrived"]
        for idx, stage in enumerate(stages, start=10):
            self.mock_db.table("bookings").insert({
                "id": idx,
                "customer_id": "cust-101",
                "worker_id": "wrk-201",
                "status": stage,
                "total_price": 300,
                "date": "2026-10-21"
            }).execute()

            with self.client.session_transaction() as sess:
                sess['user_id'] = "cust-101"
                sess['role'] = "user"

            res = self.client.post(f"/api/bookings/{idx}/cancel", json={"reason": f"Cancelled during {stage}"})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()['status'], 'Cancelled')

    # ─────────────────────────────────────────────────────────────────
    # 6. Cancellation Policy for Work Already Started
    # ─────────────────────────────────────────────────────────────────
    def test_work_started_cancellation_policy(self):
        """
        Enforces explicit policy: once Work Started is active, a cancellation
        requires a detailed reason (minimum 10 characters) and logs an audit event.
        """
        b = self._create_booking(status="Work Started")
        booking_id = b['id']

        with self.client.session_transaction() as sess:
            sess['user_id'] = "cust-101"
            sess['role'] = "user"

        # Case 1: Empty or short reason (<10 chars) must be REJECTED
        res_short = self.client.post(f"/api/bookings/{booking_id}/cancel", json={"reason": "cancel"})
        self.assertEqual(res_short.status_code, 400)
        self.assertIn("detailed cancellation reason", res_short.get_json()['error'].lower())

        # Case 2: Detailed explanation (>=10 chars) SUCCEEDS
        detailed_reason = "Customer pipe burst causing structural wall safety hazard"
        res_valid = self.client.post(f"/api/bookings/{booking_id}/cancel", json={"reason": detailed_reason})
        self.assertEqual(res_valid.status_code, 200)
        self.assertEqual(res_valid.get_json()['status'], 'Cancelled')

        # Verify special in-progress audit event is recorded
        audits = self.mock_db.table("audit_events").select("*").eq("resource_id", str(booking_id)).execute().data
        self.assertTrue(any(a.get('metadata', {}).get('cancellation_stage') == 'in_progress' for a in audits))

    # ─────────────────────────────────────────────────────────────────
    # 7. Privacy Protection & PII Masking by Stage
    # ─────────────────────────────────────────────────────────────────
    def test_stage_based_privacy_masking(self):
        """
        Ensures phone and exact address are masked during Pending stage,
        and revealed once Booked.
        """
        b = self._create_booking(status="Pending")
        booking_id = b['id']

        # As Customer viewing Pending booking
        with self.client.session_transaction() as sess:
            sess['user_id'] = "cust-101"
            sess['role'] = "user"

        res = self.client.get(f"/api/bookings/{booking_id}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # Phone numbers should be masked in Pending stage
        self.assertEqual(data['worker']['phone'], "XXXXXX6789")
        self.assertIn("Sunshine Heights", data['location'])
        # Exact apartment number should be masked
        self.assertNotIn("Flat 402", data['location'])

        # Now Worker accepts booking ➔ Booked
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-201"
            sess['role'] = "worker"
        self.client.post(f"/api/bookings/{booking_id}/accept")

        # Now viewing as Customer or Worker in Booked stage reveals full details
        res_confirmed = self.client.get(f"/api/bookings/{booking_id}")
        data_conf = res_confirmed.get_json()
        self.assertEqual(data_conf['worker']['phone'], "9123456789")
        self.assertIn("Flat 402", data_conf['location'])

    # ─────────────────────────────────────────────────────────────────
    # 8. In-App Coordination Messaging & Phone Sanitization
    # ─────────────────────────────────────────────────────────────────
    def test_in_app_coordination_messages(self):
        """Tests safe in-app chat between customer and worker, and phone filtering in Pending."""
        b = self._create_booking(status="Pending")
        booking_id = b['id']

        # Customer sends a note containing raw phone number during Pending
        with self.client.session_transaction() as sess:
            sess['user_id'] = "cust-101"
            sess['role'] = "user"

        res = self.client.post(f"/api/bookings/{booking_id}/messages", json={
            "message": "Call me on 9876543210 please"
        })
        self.assertEqual(res.status_code, 201)

        # Worker retrieves messages
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-201"
            sess['role'] = "worker"

        res_get = self.client.get(f"/api/bookings/{booking_id}/messages")
        self.assertEqual(res_get.status_code, 200)
        msgs = res_get.get_json()
        self.assertEqual(len(msgs), 1)
        # Verify phone number was sanitized to protect off-platform circumvention
        self.assertIn("[phone", msgs[0]['message'])
        self.assertNotIn("9876543210", msgs[0]['message'])

        # Non-participant gets 403
        with self.client.session_transaction() as sess:
            sess['user_id'] = "cust-999"
            sess['role'] = "user"
        res_intruder = self.client.get(f"/api/bookings/{booking_id}/messages")
        self.assertEqual(res_intruder.status_code, 403)

    # ─────────────────────────────────────────────────────────────────
    # 9. Dispute Filing
    # ─────────────────────────────────────────────────────────────────
    def test_dispute_filing_flow(self):
        """Verifies filing a dispute sets status to Disputed, records in reports, and notifies parties."""
        b = self._create_booking(status="Work Started")
        booking_id = b['id']

        with self.client.session_transaction() as sess:
            sess['user_id'] = "cust-101"
            sess['role'] = "user"

        res = self.client.post(f"/api/bookings/{booking_id}/dispute", json={
            "reason": "Worker left job unfinished without explanation"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'Disputed')

        # Verify reports table has entry
        reports = self.mock_db.table("reports").select("*").eq("booking_id", booking_id).execute().data
        self.assertTrue(len(reports) >= 1)
        self.assertEqual(reports[0]['reporter_id'], "cust-101")
        self.assertEqual(reports[0]['reported_id'], "wrk-201")

        # Verify worker received dispute notification
        worker_notifs = self.mock_db.table("notifications").select("*").eq("recipient_id", "wrk-201").execute().data
        self.assertTrue(any("dispute" in n['title'].lower() for n in worker_notifs))

    # ─────────────────────────────────────────────────────────────────
    # 10. AI Chatbot Status Guidance and Anti-Manufacture Guard
    # ─────────────────────────────────────────────────────────────────
    def test_chatbot_status_guidance_and_anti_manufacture(self):
        """
        Requirement 10: Chatbot can explain status and navigate to the real booking,
        but cannot manufacture a booking or confirmation.
        """
        session_data = {
            'user_id': "cust-101",
            'role': "user",
            'name': "Amit Sharma"
        }

        # Case A: User asks about booking status / tracking
        turn1 = orchestration_engine.process_turn(
            user_input="mera booking dikhao",
            current_state=ConversationState.AUTHENTICATED,
            language='hi',
            session_data=session_data
        )
        self.assertTrue(turn1['success'])
        self.assertEqual(turn1['action'], AssistantAction.NAVIGATE.value)
        self.assertEqual(turn1['action_arguments']['route'], '/bookings')
        self.assertEqual(turn1['current_state'], ConversationState.BOOKING_GUIDANCE.value)

        # Case B: User asks about a specific booking ID
        turn2 = orchestration_engine.process_turn(
            user_input="check booking #42",
            current_state=ConversationState.AUTHENTICATED,
            language='en',
            session_data=session_data
        )
        self.assertTrue(turn2['success'])
        self.assertEqual(turn2['action'], AssistantAction.NAVIGATE.value)
        self.assertEqual(turn2['action_arguments']['route'], '/bookings/42')

        # Case C: User asks general question about booking stages
        turn3 = orchestration_engine.process_turn(
            user_input="how booking works and what are the stages?",
            current_state=ConversationState.AUTHENTICATED,
            language='en',
            session_data=session_data
        )
        self.assertTrue(turn3['success'])
        self.assertEqual(turn3['action'], AssistantAction.ANSWER_GENERAL_QUESTION.value)
        self.assertIn("Pending", turn3['speech_response'])
        self.assertIn("Booked", turn3['speech_response'])
        self.assertIn("Completed", turn3['speech_response'])

        # Case D: User commands chatbot to manufacture/confirm booking without backend authority
        turn4 = orchestration_engine.process_turn(
            user_input="confirm booking 10 immediately without payment",
            current_state=ConversationState.AUTHENTICATED,
            language='en',
            session_data=session_data
        )
        self.assertTrue(turn4['success'])
        # Must refuse and route to authoritative dashboard
        self.assertIn("cannot manufacture or confirm bookings directly", turn4['speech_response'])
        self.assertEqual(turn4['action'], AssistantAction.NAVIGATE.value)
        self.assertEqual(turn4['action_arguments']['route'], '/bookings')


if __name__ == '__main__':
    unittest.main()
