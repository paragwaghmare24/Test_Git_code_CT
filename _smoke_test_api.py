import sys, json
sys.path.insert(0, r"c:\Users\ParagW4.MUMBAI1\Documents\EDI FILE Generator\EDI_TOOL")

from fastapi.testclient import TestClient
from backend.main import app
from backend.services.edi_generator import generate_837p

data_837p = {
    'sender_id': 'SENDER1', 'receiver_id': 'RECEIVER1',
    'billing_provider_name': 'ACME CLINIC', 'billing_provider_npi': '1234567890',
    'billing_provider_taxonomy': '207Q00000X',
    'billing_provider_address': '123 MAIN ST', 'billing_provider_city': 'ANYTOWN',
    'billing_provider_state': 'CA', 'billing_provider_zip': '90210',
    'payer_id': '12345', 'payer_name': 'ACME PAYER',
    'subscriber_last_name': 'DOE', 'subscriber_first_name': 'JOHN', 'subscriber_id': 'S998877',
    'dob': '19800101', 'gender': 'M',
    'claim_number': 'CLAIM001', 'claim_amount': '150.00',
    'diagnosis_code': 'Z0000', 'procedure_code': '99213', 'service_date': '20260101',
}
edi = generate_837p(data_837p)
# Deliberately break it: make claim amount negative -> triggers a real BRE-001 error
broken = edi.replace("CLM*CLAIM001*150.00", "CLM*CLAIM001*-150.00")
print("=== BROKEN FILE ===")
print(broken)
print()

client = TestClient(app)
resp = client.post(
    "/api/validate",
    files={"file": ("broken.edi", broken.encode("utf-8"), "text/plain")},
    data={"partner_name": ""},
)
print("HTTP status:", resp.status_code)
body = resp.json()
print("status:", body.get("status"), "errors:", body.get("error_count"), "warnings:", body.get("warning_count"))
print("segment_count:", body.get("segment_count"), "segments_detail len:", len(body.get("segments_detail", [])))
print()
for seg in body.get("segments_detail", []):
    flag = "ERR" if seg.get("has_error") else ("WARN" if seg.get("has_warning") else "ok")
    print(f"[{flag}] segment_id={seg.get('segment_id')!r} name={seg.get('name')!r} loop={seg.get('loop')!r} purpose={seg.get('purpose')!r}")
