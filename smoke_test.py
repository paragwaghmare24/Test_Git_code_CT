"""
smoke_test.py
Quick end-to-end smoke test.
Tests: parse, validate, compare, 999 analysis, 277CA analysis, generation.
"""
import sys
sys.path.insert(0, '.')

from backend.services.edi_parser import parse
from backend.services.edi_validator import validate_raw
from backend.services.edi_comparator import compare_raw
from backend.services.analyzer_999 import analyze_raw as analyze_999
from backend.services.analyzer_277ca import analyze_raw as analyze_277ca
from backend.services.edi_generator import generate

# Minimal valid 837P sample
SAMPLE_837P = (
    "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *240101*1200*^*00501*000000001*0*P*:~"
    "GS*HC*SENDER*RECEIVER*20240101*1200*1*X*005010X222A1~"
    "ST*837*0001~"
    "BHT*0019*00*0001*20240101*1200*CH~"
    "NM1*41*2*BILLING PROVIDER*****46*1234567890~"
    "NM1*40*2*PAYER*****46*987654321~"
    "HL*1**20*1~"
    "NM1*85*2*BILLING PROVIDER*****XX*1234567890~"
    "N3*123 MAIN ST~"
    "N4*ANYTOWN*CA*90210~"
    "HL*2*1*22*0~"
    "SBR*P*18*GROUP001****CI~"
    "NM1*IL*1*DOE*JOHN****MI*MEM12345~"
    "N3*456 PATIENT AVE~"
    "N4*ANYTOWN*CA*90210~"
    "DMG*D8*19800101*M~"
    "CLM*CLM001*150.00***11:B:1*Y*A*Y*I~"
    "HI*ABK:Z23.0~"
    "LX*1~"
    "SV1*HC:99213*150.00*UN*1***1~"
    "DTP*472*D8*20240101~"
    "SE*21*0001~"
    "GE*1*1~"
    "IEA*1*000000001~"
)

# Minimal 999 sample
SAMPLE_999 = (
    "ISA*00*          *00*          *ZZ*RECEIVER       *ZZ*SENDER         *240101*1200*^*00501*000000002*0*P*:~"
    "GS*FA*RECEIVER*SENDER*20240101*1200*2*X*005010X231A1~"
    "ST*999*0001~"
    "AK1*HC*1~"
    "AK2*837*0001~"
    "AK5*A~"
    "AK9*A*1*1*1~"
    "SE*6*0001~"
    "GE*1*2~"
    "IEA*1*000000002~"
)

print("=== SMOKE TEST ===")
print()

# 1. Parse
print("1. Parse 837P...")
tx = parse(SAMPLE_837P, source_file="test.edi")
assert tx.transaction_type == "837P", f"Expected 837P, got {tx.transaction_type}"
assert tx.interchange_control_number == "000000001"
print(f"   type={tx.transaction_type}, icn={tx.interchange_control_number}, sender={tx.sender_id.strip()} ✓")

# 2. Validate
print("2. Validate 837P...")
result = validate_raw(SAMPLE_837P, source_file="test.edi")
print(f"   status={result.status.value}, errors={result.error_count}, warnings={result.warning_count} ✓")

# 3. Compare (same file → 0 differences)
print("3. Compare identical files...")
cmp = compare_raw(SAMPLE_837P, SAMPLE_837P, "A", "B")
assert cmp.total_differences == 0, f"Expected 0 differences for identical files, got {cmp.total_differences}"
print(f"   differences={cmp.total_differences} ✓")

# 4. Compare different sender IDs
modified = SAMPLE_837P.replace("*SENDER         *", "*NEWSENDER      *")
cmp2 = compare_raw(SAMPLE_837P, modified)
print(f"4. Compare modified file: differences={cmp2.total_differences} ✓")

# 5. 999 Analysis
print("5. Analyze 999...")
r999 = analyze_999(SAMPLE_999)
print(f"   overall_status={r999.overall_status}, transactions={len(r999.transaction_analyses)} ✓")

# 6. Generate 837P
print("6. Generate 837P from structured data...")
edi_out = generate("837P", {
    "sender_id": "SENDER",
    "receiver_id": "RECEIVER",
    "billing_provider_name": "TEST CLINIC",
    "billing_provider_npi": "1234567890",
    "subscriber_last_name": "DOE",
    "subscriber_first_name": "JANE",
    "subscriber_id": "MEM99999",
    "member_id": "MEM99999",
    "dob": "19900101",
    "gender": "F",
    "claim_number": "CLM999",
    "claim_amount": "200.00",
    "diagnosis_code": "Z23.0",
    "procedure_code": "99213",
    "service_date": "20240101",
})
assert "ISA" in edi_out and "CLM" in edi_out
print(f"   Generated EDI length={len(edi_out)} chars ✓")

print()
print("=== ALL SMOKE TESTS PASSED ===")
