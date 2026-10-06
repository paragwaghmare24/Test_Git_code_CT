"""
Enhancement verification test — run against live backend on :8000
"""
import requests

BASE = "http://127.0.0.1:8000/api"

EDI_837 = (
    "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       "
    "*231214*1516*^*00501*000000001*0*P*:~\n"
    "GS*HC*SENDER*RECEIVER*20231214*151600*1*X*005010X222A1~\n"
    "ST*837*0001*005010X222A1~\n"
    "BPR*I*100.00*C*ACH*CCP*01*111111111*DA*123456789*1234567890**01*111111111*DA*987654321*20231214~\n"
    "NM1*IL*1*DOE*JOHN*A***MI*123456789~\n"
    "CLM*CLAIM001*500.00***11:B:1*Y*A*Y*I~\n"
    "SV1*HC:99213*100.00*UN*1**1~\n"
    "CLM*CLAIM002*400.00***11:B:1*Y*A*Y*I~\n"
    "SV1*HC:99214*200.00*UN*1**1~\n"
    "SE*9*0001~\n"
    "GE*1*1~\n"
    "IEA*1*000000001~"
)

EDI_837_B = EDI_837.replace("CLAIM002*400.00", "CLAIM002*450.00")

EDI_999 = (
    "ISA*00*          *00*          *ZZ*RECV           *ZZ*SEND           "
    "*231214*1516*^*00501*000000002*0*P*:~\n"
    "GS*FA*RECV*SEND*20231214*151600*2*X*005010X231A1~\n"
    "ST*999*0001*005010X231A1~\n"
    "AK1*HC*1*005010X222A1~\n"
    "AK9*A*1*1*1~\n"
    "SE*3*0001~\n"
    "GE*1*2~\n"
    "IEA*1*000000002~"
)

results = {}


def check(name, passed, detail=""):
    results[name] = ("PASS", detail) if passed else ("FAIL", detail)


# 1. Parse 837P
r = requests.post(BASE + "/parse", files={"file": ("test.edi", EDI_837.encode())})
j = r.json()
check("1. Parse 837P", j.get("transaction_type") == "837P", j.get("transaction_type", "?"))

# 2. Validate — segments_detail present (Stedi-like inspector)
r2 = requests.post(BASE + "/validate", files={"file": ("test.edi", EDI_837.encode())})
j2 = r2.json()
has_seg = "segments_detail" in j2
seg_count = len(j2.get("segments_detail", []))
check("2. Validate segments_detail", has_seg, f"{seg_count} segments" if has_seg else str(list(j2.keys())))

# 3. Compare — CLM-based record matching for 837
r3 = requests.post(BASE + "/compare", files={"file_a": ("a.edi", EDI_837.encode()), "file_b": ("b.edi", EDI_837_B.encode())})
j3 = r3.json()
rl = j3.get("record_level_used", False)
check(
    "3. Compare CLM-match",
    rl,
    f"label={j3.get('record_label')} matched={j3.get('matched_records_count')} diffs={j3.get('total_differences',0)}"
)

# 4. Excel export
r4 = requests.post(BASE + "/export", files={"file": ("test.edi", EDI_837.encode())})
check("4. Export Excel", r4.status_code == 200, f"HTTP {r4.status_code}, {len(r4.content)} bytes")

# 5. 999 analyze
r5 = requests.post(BASE + "/analyze/999", files={"file": ("999.edi", EDI_999.encode())})
j5 = r5.json()
check("5. Analyze 999", bool(j5.get("overall_status")), j5.get("overall_status", "?"))

# 6. AI gate — request
r6 = requests.post(BASE + "/ai/request", json={"action": "Explain NM1", "context": "test"})
j6 = r6.json()
check("6. AI Gate request", "request_id" in j6, str(list(j6.keys())))

# 7. Generate 837P  (endpoint: POST /api/generate, body: {transaction_type, data:{...}})
gen_payload = {
    "transaction_type": "837P",
    "data": {
        "sender_id": "SENDER", "receiver_id": "RECEIVER",
        "billing_provider_name": "TEST CLINIC", "billing_provider_npi": "1234567890",
        "subscriber_last_name": "DOE", "subscriber_first_name": "JOHN",
        "subscriber_id": "MEM001", "member_id": "MEM001",
        "dob": "19800101", "gender": "M",
        "claim_number": "CLM001", "claim_amount": "500.00",
        "diagnosis_code": "Z23.0", "procedure_code": "99213", "service_date": "20231201",
    }
}
r7 = requests.post(BASE + "/generate", json=gen_payload)
j7 = r7.json()
# response field is 'edi', not 'edi_content'
check("7. Generate 837P", bool(j7.get("edi")), f"{len(j7.get('edi',''))} chars")

# 8. Companion guides list  (response: {"guides": [...]})
r8 = requests.get(BASE + "/companion-guides")
j8 = r8.json()
guides = j8.get("guides", j8) if isinstance(j8, dict) else j8
check("8. Companion Guides", isinstance(guides, list) and len(guides) > 0, f"{len(guides)} guides")

# 9. TP mappings  (response: {"mappings": [...]}, 0 when none uploaded)
r9 = requests.get(BASE + "/tp-mappings")
j9 = r9.json()
maps = j9.get("mappings", j9) if isinstance(j9, dict) else j9
check("9. TP Mappings endpoint", r9.status_code == 200, f"{r9.status_code}: {len(maps)} mappings")

# --- Print results ---
print()
print("=" * 60)
print("  ENHANCEMENT VERIFICATION TEST RESULTS")
print("=" * 60)
maxk = max(len(k) for k in results)
all_pass = True
for k, (status, detail) in results.items():
    if status != "PASS":
        all_pass = False
    marker = "✓" if status == "PASS" else "✗"
    print(f"  {marker}  {k:<{maxk}}  {status:<4}  {detail}")
print("=" * 60)
print(f"  OVERALL: {'ALL PASS ✓' if all_pass else 'SOME FAILURES — see above'}")
print("=" * 60)
print()
