"""Exact contextual inverse adapters shared by inherited byte contracts.

No production file is exempted: approved changes must match their complete
unique after-hunks and recover the immutable immediate-base SHA-256.
"""
from pathlib import Path
import hashlib
import json

INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3331_inverse.json').read_text())
assert INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.0'


NEW_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3332_inverse.json').read_text())
assert NEW_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.1'


RX_FLAGS_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3333_inverse.json').read_text())
assert RX_FLAGS_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.2'


TRANSPORT_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3334_inverse.json').read_text())
assert TRANSPORT_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.3'


BUILD_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3334_1_inverse.json').read_text())
assert BUILD_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.4'


PRIORITY_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3335_inverse.json').read_text())
assert PRIORITY_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.4.1'


PRIORITY_BUILD_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3335_1_inverse.json').read_text())
assert PRIORITY_BUILD_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.5'


CONTEXT_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3336_inverse.json').read_text())
assert CONTEXT_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.5.1'


TIMING_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3337_inverse.json').read_text())
assert TIMING_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.6'


RX_NEIGHBORHOOD_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3338_inverse.json').read_text())
assert RX_NEIGHBORHOOD_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.7'


AUDIT_FIXES_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3339_inverse.json').read_text())
assert AUDIT_FIXES_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.8'


CURRENT_MUX1_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v33310_inverse.json').read_text())
assert CURRENT_MUX1_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.9'



SETTINGS_CAPTURE_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v33311_inverse.json').read_text())
assert SETTINGS_CAPTURE_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.10'



PARK_RETRY_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v33312_inverse.json').read_text())
assert PARK_RETRY_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.11'


FIXED_MODE1_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3340_inverse.json').read_text())
assert FIXED_MODE1_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.33.12'

BODY_ISOLATION_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3341_inverse.json').read_text())
assert BODY_ISOLATION_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.0'

PARK_LATENCY_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3342_inverse.json').read_text())
assert PARK_LATENCY_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.1'

MUX_BOUNDARY_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3343_inverse.json').read_text())
assert MUX_BOUNDARY_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.2'

INPUT_LATENCY_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3344_inverse.json').read_text())
assert INPUT_LATENCY_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.3'

AP_RETRY_SCHEDULING_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3345_inverse.json').read_text())
assert AP_RETRY_SCHEDULING_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.4'

QUEUED_RX_PRIORITY_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3346_inverse.json').read_text())
assert QUEUED_RX_PRIORITY_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.5'

RETRY_DISPATCH_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3347_inverse.json').read_text())
assert RETRY_DISPATCH_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.6'

FOUR_PATHS_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3348_inverse.json').read_text())
assert FOUR_PATHS_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.7'

ULC_MUTEX_INVERSE = json.loads((Path(__file__).parent / 'fixtures/diagnostic_v3349_inverse.json').read_text())
assert ULC_MUTEX_INVERSE['basePackage'] == 'P4-CAN-Universal-v3.34.8'

def approved_base_bytes(relative, data):
    for layer in (ULC_MUTEX_INVERSE, FOUR_PATHS_INVERSE, RETRY_DISPATCH_INVERSE, QUEUED_RX_PRIORITY_INVERSE, AP_RETRY_SCHEDULING_INVERSE, INPUT_LATENCY_INVERSE, MUX_BOUNDARY_INVERSE, PARK_LATENCY_INVERSE, BODY_ISOLATION_INVERSE, FIXED_MODE1_INVERSE, PARK_RETRY_INVERSE, SETTINGS_CAPTURE_INVERSE, CURRENT_MUX1_INVERSE, AUDIT_FIXES_INVERSE, RX_NEIGHBORHOOD_INVERSE, TIMING_INVERSE, CONTEXT_INVERSE, PRIORITY_BUILD_INVERSE, PRIORITY_INVERSE, BUILD_INVERSE, TRANSPORT_INVERSE, RX_FLAGS_INVERSE, NEW_INVERSE, INVERSE):
        if relative not in layer['files']:
            continue
        adapter = layer['files'][relative]
        text = data.decode()
        for hunk in adapter['hunks']:
            assert text.count(hunk['after']) == 1, relative + ': diagnostic adapter no longer exact'
            text = text.replace(hunk['after'], hunk['before'], 1)
        data = text.encode()
        assert hashlib.sha256(data).hexdigest() == adapter['baseSha256'], relative + ': unauthorized base change'
    return data
