# P4-CAN Universal v3.29.3 — Validation

Base: completed v3.29.2, retaining the user-selected `v3.29.1-P4-3TWAI-net2` wiring and routes. Target: ESP32-P4 post-v3, Arduino-ESP32 3.3.12 / ESP-IDF 5.5.5, Hosted C6 radio over SDIO.

## Reported failure and implementation

Both new device screenshots report `security failed: i=2 e=1291 sm=-1 d=-1`. SDK headers decode `1291 = 0x50b` as peer SMP DHKey Check Failed. `i=2` means a security procedure was already active; the unobserved SMP/disconnect results remain -1. This does not by itself identify which side started pairing.

The installed P4 SDK enables TinyCrypt and hardware ECC, matching Espressif IDF issue 19002 and Hosted issue 241. The upstream correction is pinned to commit `9fd7cb7e606a06111e1b14be7f4e00d77d9cf3dd`. All five ECC/port source/header files are included byte-exact, with licenses and a source manifest. The installed SDK archive is left unchanged. Native NimBLE, the original CSPRNG, bonding and Secure Connections remain enabled.

## Behavioral regression and review evidence

- Workflow RED compiled and executed the original v5.5.5 C successfully, then failed the Bluetooth Core DHKey known-answer assertion. HAL doubles compute independent affine P-256 arithmetic; they do not return a constant expected secret. Per-file SOC visibility reproduces the original 257-bit regularization / 256-bit hardware truncation defect.
- With the actual fixed production C, seven arithmetic tests pass, including the Bluetooth vector, 26 differential ECDH calculations with/without blinding, canonical hardware public-key generation and invalid-point rejection. Regularized ECDH must not reach the hardware scalar callback. The upstream's existing failure outputs for scalars 1, N-1 and N-2 are characterized as zero/return-failure, not counted as successful ECDH vectors.
- The runtime known-answer helper exercises the actual native NimBLE DHKey API. Host tests verify the LE API inputs, correct answer, corrupted answer and native API error. The actual calculation still requires device execution.
- Independent read-only review found a host lifetime leak on known-answer failure. A production-init regression first failed, then passed after explicit observer removal and host deinitialization. It covers cached boot failure, successful start and successful-check reuse after Master OFF/ON. Final re-review found no remaining actionable issue in scope.
- Link-checker contracts verify live ELF32/RISC-V function addresses, map owners, upstream source hashes, missing/wrong owners and old SDK ECC members. The workspace publisher runs the package checker after compilation and before artifact creation; failure blocks publication. The complete related workspace tool contract suite passes 68/68 tests.

## Final host and generated-asset evidence

Final fresh completion passed: Python 6/6 original files / 6 execution units, C++ 3/3 binaries and JavaScript 1/1 suite, in 4.749 seconds. The companion `host-validation.json` retains commands and outputs.

Two independent dashboard generations are byte-identical to the existing header: 365,384 source bytes, 82,209 gzip bytes; decompression matches the editable source. Header SHA-256: `66b9d2a3c1fb27c4f30490176516c8d85ed29638cd119544eca13372d3613477`.

Final P4 compiler/link results, exact target configuration, selected crypto owners, compiler output, resource usage, source snapshot consistency and paired artifact hashes are recorded in the companion `releases/P4-CAN-Universal-v3.29.3/build-evidence.json`. The publisher requires the actual ELF/map checks to pass before creating either artifact. No target success is inferred from host results.

## Preserved behavior and unverified areas

The original CAN adapter/core/runtime, pins, vehicle profiles/routes, NVS schema and editable dashboard remain byte-identical to the recorded net2 baseline. The v3.29.2 asynchronous discovery, fresh-address reuse and bounded security behavior are retained. New statistics fields do not alter the dashboard's visual design or interactions. JavaScript tests use a mocked DOM/API; no new real-browser render is claimed for the unchanged dashboard.

No P4/C6 flash, serial-device access, live CAN transmission, physical BLE or vehicle test, or road test was performed. Successful registration of the reported button, actual pairing speed, runtime known-answer outcome, wireless coexistence and long-run stability remain unverified. No full release ZIP, external publication or Git commit is created. The inherited validation sections below are historical evidence only.

# P4-CAN Universal v3.29.2 — Validation

Base: user-confirmed `v3.29.1-P4-3TWAI-net2`. Target: ESP32-P4 post-v3, Arduino-ESP32 3.3.12, ESP-Hosted C6 over SDIO.

## Current scope

- Original net2 pin configuration, CAN adapter, CAN core/runtime, vehicle profile/logic and editable dashboard are byte-identical to their recorded baseline hashes. The separate net2-pinmap1 source is not selected.
- Behavioral RED was confirmed through the firmware workflow after successful host compilation, before the corresponding implementation: queued Pair waits for the old discovery timeout; the old security consumer enters an indefinite SDK wait; review regressions expose unsafe scan-result deletion and implicit ATT-error reauthentication.
- Focused host files pass after fixes. Pairing covers selection interruption, queue rejection, cancellation, target fallback, typed-address freshness and callback lifetime. Security exercises both operational and identity-probe consumers, actual encryption, status retention, cancellation, peer isolation, clock wrap, bounded missing-key repair and host/listener lifecycle.
- Independent read-only BLE review completed before final validation. Its material findings were addressed with new failing regressions and focused GREEN: host callback lifetime, Arduino GATT retry ownership and normally hidden probe diagnostics. The SDK itself is unchanged. Its own missing-key deletion may occur in addition to the adapter's one explicit repair; host adapter call counts are not a total SDK-wide deletion count.
- A real P4 compiler syntax check against installed board/core/library headers succeeded during staging. This does not establish final linking or artifact validity.

- The first full host invocation stopped because the original P4 test expected a separate `tests/fakes` include path. Added host-only forwarding headers under the shared runner's `tests/` include root; the focused P4 regression then passed. Production CAN files and fake behavior are unchanged. This infrastructure failure is not a behavioral RED.

## Final evidence

Final fresh completion passed: Python 3/3 original files/execution units, C++ 2/2 binaries and JavaScript 1/1 suite, in 2.756 seconds. The companion `host-validation.json` retains commands and full outputs. The JavaScript suite executes mocked DOM/API fixtures; no new real-browser rendering was performed because the editable dashboard is unchanged.

Two independent dashboard generations match: 365,384 source bytes and 82,209 gzip bytes. Generated header SHA-256: `66b9d2a3c1fb27c4f30490176516c8d85ed29638cd119544eca13372d3613477`. Decompression matches the editable source byte-for-byte.

The paired publisher records the exact target, compiler output, resource usage, image identity, source consistency and artifact hashes in `releases/P4-CAN-Universal-v3.29.2/build-evidence.json`. No target success is inferred from host results.

## Unverified areas

No controller/C6 flash, serial-device access, live CAN transmission, physical BLE or vehicle test, or road test was performed. The reported button's successful P4 connection, real pairing latency, wireless coexistence and long-run behavior remain unverified. No full release ZIP, external publication or Git commit is created.

# Validation P4-CAN — 25 octobre 2026

Cible : Waveshare ESP32-P4-WIFI6, silicium 3.2, ESP32-C6 avec ESP-Hosted déjà installé.

## Correctif net2 : réseau et absence de RX signalée

Référence examinée : `C:/Users/xmick/Desktop/P4_CAN_Hosted/P4_CAN_Hosted/P4_CAN_Hosted.ino`, SHA-256 `73ac4b10d70c1b9257fb95aa91b48ee469a4e3b213cdff8c6716f90353cf50f4`.

Le portage précédent pouvait initialiser le Bluetooth en parallèle du Wi-Fi et désactivait le point d'accès/transport avant de le relancer. La séquence reprend maintenant celle du sketch fourni : GPIO6 en entrée, broches Hosted, `WiFi.mode(WIFI_AP)` contrôlé, configuration 192.168.4.1, puis point d'accès. Le Bluetooth attend ce premier démarrage réussi. Les messages de diagnostic sont émis au démarrage avant la tâche USB.

La revue TWAI a confirmé les API `_v2`, trois handles distincts, les broches demandées, le débit 500 kbit/s et le filtre ouvert. Le démarrage se fait maintenant dans l'ordre physique 0/1/2. Les trois routes partagent une réception native non bloquante et les compteurs RX sont incrémentés avant les traitements véhicule. Le taux d'échantillonnage des états passe à 100 ms. Les files de l'application restent conservées, comme expliqué dans le README.

L'utilisateur constate RUNNING sans réception sur les trois bus. Aucune cause unique n'est prouvée par la lecture du code seule et la reprise de RX après modification reste à confirmer sur la carte. Les diagnostics exposent désormais, pour chaque contrôleur, l'erreur d'initialisation, le mode, les appels RX, la dernière réponse du pilote, les files et les erreurs TEC/REC. Ces données évitent de confondre un pilote démarré avec une réception effectivement validée.

Tests supplémentaires réussis :

- `tests/test_network.cpp`, avec ASan/UBSan : ordre des opérations de la référence, GPIO6 en entrée, IP fixe, échecs de broches/Wi-Fi/adresse/AP, nouvelles tentatives, absence de redémarrage Hosted lors d'un changement de paramètres et autorisation différée du BLE.
- `tests/test_p4.cpp` : compteurs de réception et appels indépendants des trois contrôleurs, dernier résultat RX et télémétrie TEC/REC/file sur le bus supplémentaire.
- `tests/test_dashboard.js` : rendu complet des diagnostics avec valeurs RX différentes sur les trois bus et versions Hosted.
- `tests/render_dashboard.py` : page Diagnostics / Recovery vérifiée dans Edge à 360, 430 et 1024 pixels ; trois cartes physiques avec broches et compteurs distincts, aucun ancien libellé CAN A/B sur cette page, aucune erreur JavaScript ni débordement horizontal. Capture simulée : `artifacts/diagnostics-three-buses-simulated.png`.

## Tests sur PC

- `tests/test_p4.cpp` : compilation g++ avec `-Wall -Wextra -Werror -fsanitize=address,undefined`, exécution réussie. Le test utilise les vrais en-têtes d'adaptation P4, de profils, du protocole USB et de filtrage des captures avec un pilote TWAI simulé. Il couvre les cinq profils, les broches, les trois modes écoute seule, la conservation du bus d'origine à l'envoi, les trames invalides, les échecs d'installation/démarrage/désinstallation, l'attente de récupération et les numéros USB 1 à 3.
- `tests/test_dashboard.py` : cinq scripts JavaScript valides, identifiants DOM uniques, trois bus présents, choix de profil fixe, identité entre le HTML source et sa version embarquée décompressée, contrôle du transport et du renommage.
- `tests/test_dashboard.js` : exécution des fonctions du dashboard pour les cinq profils, choix du type de commandes Highland, rendu distinct des trois états de trafic et correspondance des trois bus physiques dans le panneau de capture (profils standard et Y L).
- `tests/render_dashboard.py` : rendu réel dans Edge sans erreur JavaScript, contrôlé à 360, 430 et 1024 pixels. Les trois cartes restent visibles et alignées, sans débordement horizontal. BODY et PARTY sont simulés actifs, CHASSIS en bus-off. L'image `artifacts/dashboard-three-buses-simulated.png` provient de cette simulation.

Commandes, depuis le dossier du projet :

```powershell
python -X utf8 tests/test_dashboard.py
node tests/test_dashboard.js
python -X utf8 tests/render_dashboard.py
```

Pour le test C++, dans WSL Debian après s'être placé dans le même dossier :

```sh
g++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined -Itests/fakes -I. tests/test_p4.cpp -o /tmp/p4can_test
/tmp/p4can_test
g++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined -I. tests/test_network.cpp -o /tmp/p4network_test
/tmp/p4network_test
```

Le rendu Edge nécessite le module Python Playwright ; le chemin du navigateur Windows est explicite dans le script.

## Compilation finale net2

Compilation finale Arduino-ESP32 3.3.12 réussie pour `v3.29.1-P4-3TWAI-net2` (`exitCode: 0`), avec `sourceMatchesWorkspace: true`.

- Programme : **1 384 180 octets / 4 718 592** (29 %).
- Variables globales : **77 560 octets / 327 680** (23 %), 250 120 octets restants selon le rapport du compilateur. Ce chiffre ne représente pas la mémoire libre après les allocations à l'exécution.
- Cible : `esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio`.
- Application : `P4-CAN-build/firmware/P4-CAN-Universal-v3.29.1.ino.bin`.
- Image complète : `P4-CAN-build/firmware/P4-CAN-Universal-v3.29.1.ino.merged.bin`.

Le script `tools/build_p4.py` produit `P4-CAN-build/compile.log` et `P4-CAN-build/manifest.json` dans le dossier voisin. Le manifeste contient la cible exacte, le résultat de compilation et les empreintes SHA-256 des sources et des binaires ; `sourceMatchesWorkspace` vérifie qu'aucune source n'a changé pendant la compilation.

## Limites

Aucun matériel flashé. Aucun essai de communication réelle avec le C6, de Wi-Fi/BLE, de transceiver, de bus CAN ou de véhicule. Les tests sur PC ne mesurent ni les ACK ni la charge, la latence et la récupération des trois réseaux physiques. Les tests ciblés ne simulent pas l'intégralité des fonctions du véhicule.

L'original et les fichiers retirés du projet sont conservés hors du livrable dans `P4-CAN-migration-backup` sur le Bureau. Les anciens résultats de validation ne sont pas repris comme preuve de fonctionnement sur P4.
