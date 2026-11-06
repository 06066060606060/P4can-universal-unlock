#pragma once
/* Deliberately visible only to sources that include the SOC header. In v5.5.5
 * ecc.c includes this through the port; ecc_dh.c does not. A global -D would
 * hide the SDK's mismatched scalar-regularization bug. */
#define SOC_ECC_SUPPORTED 1
#define SOC_ESP_NIMBLE_CONTROLLER 0
