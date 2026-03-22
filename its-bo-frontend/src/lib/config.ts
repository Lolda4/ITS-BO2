/* API configuration */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const API_V1 = `${API_BASE}/api/v1`;

/** Polling interval for system status (ms) */
export const STATUS_POLL_MS = 2000;

/** Network condition presets for display */
export const NETWORK_CONDITIONS: Record<string, string> = {
  lab_amarisoft_lte:    "Lab – Amarisoft LTE",
  lab_amarisoft_5g_nsa: "Lab – Amarisoft 5G NSA",
  field_tmobile_4g:     "Field – T-Mobile 4G",
  field_o2_4g:          "Field – O2 4G",
  field_vodafone_4g:    "Field – Vodafone 4G",
  field_tmobile_5g:     "Field – T-Mobile 5G",
  custom:               "Custom",
};
