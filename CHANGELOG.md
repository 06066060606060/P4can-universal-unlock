# P4-CAN Universal v3.29.3 — 2026-10-27

- Backport Espressif's complete P4 TinyCrypt ECC fix (`9fd7cb7e606a06111e1b14be7f4e00d77d9cf3dd`) as package-owned C objects. Correct native/peripheral conversion and regularized 257-bit ECDH handling associated with peer DHKey Check Failed (`1291`). Keep Secure Connections, native randomness and bonding enabled.
- Check the actual linked NimBLE DHKey path with the Bluetooth Core known-answer vector before allowing BLE operations. A failure stops the host and blocks pairing for the boot; API statistics retain the check result.
- Verify final ELF/map ownership and reject the old SDK ECC archive members before OTA artifact publication. Add actual-C arithmetic regressions, original-code failure evidence and failure-path lifecycle checks.
- Retain the v3.29.2 discovery speed improvements and bounded security behavior. Preserve the user-confirmed net2 wiring, CAN policies, NVS schema and dashboard bytes. The installed SDK and completed packages are unchanged.

# P4-CAN Universal v3.29.2 — 2026-10-27

- Repair the P4 NimBLE security flow with one native owner, actual-encryption verification, a bounded and cancellable ten-second security wait, one confirmed missing-key repair, and detailed failure codes. Preserve native SC bonding while preventing Arduino GATT errors from reentering its unbounded security helper.
- Stop manual discovery promptly after Pair selection, reuse recent typed discovery addresses and retain the fresh-scan fallback for missing or expired observations. Keep multi-candidate selection and existing dashboard interactions.
- Drain host callbacks before clearing scan results or reusing BLE state. Retain operational and probe diagnostics independently of heavy logging.
- Preserve the user-selected net2 CAN pin map, YL/other vehicle routes, CAN/NVS implementation and editable dashboard bytes. Create fresh paired artifacts rather than reusing the original archive's older BIN.

# Changements du portage P4 — 25 octobre 2026

## Correctif réseau et diagnostics — net2

- Séquence réseau reprise du sketch fonctionnel fourni : GPIO6 en entrée, initialisation SDIO avant Wi-Fi, contrôle des erreurs, IP 192.168.4.1, aucune désactivation Hosted au démarrage et Bluetooth autorisé après le premier point d'accès réussi.
- Messages de démarrage avant le journal USB ; conservation des identifiants NVS lors d'un échec temporaire.
- Démarrage TWAI dans l'ordre physique 0/1/2 ; réception native non bloquante commune aux trois bus et comptage avant les traitements véhicule.
- Échantillonnage des états à 100 ms ; Diagnostics / Recovery présente BODY, CHASSIS et PARTY avec erreurs, appels RX et files indépendantes.
- Aucun flash ni essai matériel ; la cause unique de l'absence de RX rapportée reste à confirmer sur la carte.

## Portage initial

- Trois contrôleurs TWAI natifs, bus physiques BODY 20/21, CHASSIS 22/23, PARTY 26/27.
- Tous les profils utilisent les trois bus ; ancien VH Y L raccordé à BODY.
- ESP-Hosted C6 par SDIO, configuré avant Wi-Fi et Bluetooth.
- Réception, récupération, maintenance et écoute seule couvrent les trois contrôleurs.
- Accueil web à trois bus, télémétrie physique, captures de recherche et USB protocole 2.
- Suppression du pilote CAN externe et de son ancien transport matériel.
- Les anciennes notes de validation et l'historique du projet initial sont préservés dans l'archive de sauvegarde externe créée avant modification. Leurs résultats ne constituent pas une validation du P4.

- Nom P4-CAN dans le projet, le dashboard, le SSID par défaut, le BLE, les exports et les identifiants internes.
- Retrait de 19 en-têtes inaccessibles depuis le sketch et les tests, ainsi que de la prévisualisation ancienne et des binaires préliminaires. Les deux en-têtes de structure toujours utilisés sont renommés.
