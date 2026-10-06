import sys
sys.path.insert(0, '.')

modules = [
    ('backend.models.schemas', 'EDITransactionSchema'),
    ('backend.engines.hipaa_engine', 'validate'),
    ('backend.engines.companion_guide_engine', 'list_available_guides'),
    ('backend.engines.tp_mapping_engine', 'list_loaded_mappings'),
    ('backend.engines.business_rules_engine', 'validate'),
    ('backend.services.edi_parser', 'parse'),
    ('backend.services.edi_validator', 'validate_raw'),
    ('backend.services.edi_comparator', 'compare_raw'),
    ('backend.services.auto_correction', 'propose_corrections'),
    ('backend.services.analyzer_999', 'analyze_raw'),
    ('backend.services.analyzer_277ca', 'analyze_raw'),
    ('backend.services.edi_to_excel', 'export_to_excel'),
    ('backend.services.edi_generator', 'generate'),
    ('backend.main', 'app'),
]

all_ok = True
for mod, sym in modules:
    try:
        m = __import__(mod, fromlist=[sym])
        getattr(m, sym)
        print(f'OK  {mod}')
    except Exception as e:
        print(f'ERR {mod}: {e}')
        all_ok = False

print()
print('ALL OK' if all_ok else 'SOME ERRORS FOUND')
