# FSD Visualisation (Experimental)

Settings contains three controls: Enable FSD injections, Suspend FSD during AP,
and Enable "FSD Visualisation". The final toggle selects UI_enableFullSelfDriving
raw 1 (ON) or 0 (OFF), CHASSIS 0x3FD MUX0 bit46. Master OFF stops FSD echoes.
Original bit46 readback remains visible. No FSD MUX2 echoes or other FSD fields.
Shared TLSSC composition and existing transport gates remain effective.

All three settings persist in features/fsd. Old additional signal and route bits
are ignored when loading; new saves retain only marker, master, AP suspension,
and the bit46 selection (legacy values mask bit1). Unknown/stale AP status blocks
FSD when suspension is enabled; a fresh manual state resumes it.

GET /api/fsd/stats returns values 0 or 2 and stock1 (raw bit46).
POST /api/fsd/update requires enabled and values (0 or 2); optional suspendDuringAp.
S3XY FSD Visualisation toggles the saved master and preserves both other settings.
