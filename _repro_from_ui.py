"""Repro the exact broken text observed in the live UI's Raw EDI File panel."""
import json
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

# Exact text dumped in the live UI's "Raw" field for segment #1 (the entire file
# collapsed into what the UI reported as "1 of 1 segments").
raw = (
    "ISA*00*          *00*          *ZZ*100000         *ZZ*144699         *20251223*1937*%*00501*001155010*0*T*:"
    "GS*HC*77058*144699*20251223*1937*1155010*X*005010X223A2"
    "ST*837*0001*005010X223A2"
    "BHT*0019*00*51667318*20251223*170249*CH"
    "NM1*41*2*CLAIM.MD*****46*145610"
    "PER*IC*EDI SERVICES*TE*8557576060*EM*EDI@CLAIM.MD"
    "NM1*40*2*PRES TURQUOISE CARE*****46*77058"
    "HL*1**20*1"
    "PRV*BI*PXC*261QF0400X"
    "NM1*85*2*LOS LUNAS MEDICAL*****XX*1902993132"
    "N3*145 DON PASQUAL RD"
    "N4*LOS LUNAS*NM*870318841"
    "REF*EI*850224409"
    "PER*IC*LOS LUNAS MEDICAL*TE*5058654618"
    "NM1*87*2"
    "N3*PO BOX 912678"
    "N4*DENVER*CO*802912678"
    "HL*2*1*22*0"
    "SBR*P*18*A0000050******MC"
    "NM1*IL*1*MARRUFO RIVERA*MARIA*C***MI*10621720300"
    "N3*19 PEREA RD"
    "N4*PERALTA*NM*87042"
    "DMG*D8*19731105*F"
    "NM1*PR*2*PRES TURQUOISE CARE*****PI*NMPHP"
    "N3*PO BOX 27489"
    "N4*ALBUQUERQUE*NM*87125"
    "CLM*68761X94090*217.49***77:A:1**A*Y*Y"
    "DTP*434*RD8*20250801-20250801"
    "CL1*9*9*01"
    "REF*EA*94090"
    "REF*D9*25357573000006330"
    "HI*ABK:R1310"
    "NM1*71*1*JEANSONNE*SCOTT****XX*1902034879"
    "PRV*AT*PXC*207Q00000X"
    "LX*1"
    "SV2*0521*HC:T1015*217.49*UN*1**0"
    "DTP*472*D8*20250801"
    "REF*6R*181594"
    "LX*2"
    "SV2*0521*HC:99213*0*UN*1**0"
    "DTP*472*D8*20250801"
    "REF*6R*181595"
    "SE*41*0001"
    "GE*01*1155010"
    "IEA*1*001155010"
)

print("LENGTH:", len(raw))
print("Contains newline:", "\n" in raw)
print("Contains tilde:", "~" in raw)
print("Char at pos 105:", repr(raw[105:110]))

resp = client.post(
    "/api/validate",
    files={"file": ("repro.edi", raw.encode(), "text/plain")},
    data={"partner_name": ""},
)
print("STATUS:", resp.status_code)
data = resp.json()
print("status:", data.get("status"))
print("transaction_type:", data.get("transaction_type"))
print("segment_count:", data.get("segment_count"))
print("errors:", json.dumps(data.get("errors"), indent=2)[:2000])
print("warnings:", json.dumps(data.get("warnings"), indent=2)[:1000])
segs = data.get("segments_detail") or data.get("segments") or []
print("num segments_detail:", len(segs))
for s in segs[:5]:
    print(s.get("segment_id"), "|", (s.get("name") or "")[:40], "|", (s.get("raw") or "")[:60])
