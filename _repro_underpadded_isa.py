"""Verify the root-cause theory: under-padded ISA header breaks fixed-position
terminator detection even though the file uses '~' consistently throughout."""
from backend.services import edi_parser

# Realistic file: proper '~' terminator after every segment, but ISA02/04/06/08
# are NOT padded to the conventional 10/10/15/15 fixed widths (a common
# real-world deviation -- many EDI generators/hand-built test files don't pad).
raw = (
    "ISA*00*A*00*B*ZZ*SENDER*ZZ*RECEIVER*251223*1937*^*00501*000000001*0*P*:~"
    "GS*HC*SENDER*RECEIVER*20251223*1937*1*X*005010X222A1~"
    "ST*837*0001*005010X222A1~"
    "BHT*0019*00*123*20251223*1937*CH~"
    "NM1*41*2*ACME*****46*123~"
    "SE*5*0001~"
    "GE*1*1~"
    "IEA*1*000000001~"
)

print("len:", len(raw), "char@105:", repr(raw[105]) if len(raw) > 105 else "N/A")
element_sep, component_sep, segment_term = edi_parser._detect_separators(raw)
print("element_sep:", repr(element_sep), "component_sep:", repr(component_sep), "segment_term:", repr(segment_term))

tx = edi_parser.parse(raw)
n_segments = sum(len(ts.segments) + 2 for g in tx.groups for ts in g.transaction_sets)  # rough
print("groups:", len(tx.groups))
for g in tx.groups:
    for ts in g.transaction_sets:
        print("transaction_type:", ts.transaction_type, "inner segments:", len(ts.segments))
