# Dataset-to-simulator mapping

The dataset informs domain vocabulary and candidate relationship design. It is not loaded into simulation runs. The data is synthetic, event tables repeat entity identifiers by design, and README-documented history defects make it unsuitable as live state or unvalidated training evidence.

| Dataset table/fields | Simulator use | Caveat |
|---|---|---|
| `agents.agent_id`, `status`, `vendor_id` | Agent entity vocabulary and provider association | Historical status is not current availability; repeated agent IDs and vendor links are inconsistent |
| `agent_sessions.agent_id`, `login_at`, `logout_at` | Session concepts for future fixtures | Sessions are historical and do not prove live presence; times span zones |
| `borrowers.borrower_id`, `state` | Borrower entity vocabulary | Name, phone, and email are excluded; borrower identifiers repeat and contact fields are missing |
| `accounts.account_id`, `borrower_id`, `dpd`, `risk_segment`, `status` | Account/campaign eligibility fields for future synthetic fixtures | Borrower links may be absent; status policy and legal contact rules are unspecified |
| `campaigns.campaign_id`, `channel`, `strategy_version` | Campaign selection concepts | Inconsistent campaign definitions and mixed channels; no runtime import |
| `daily_targeting.account_id`, `priority`, `status` | Priority queue concept | Repeated accounts and historical queue states; simulator uses synthetic integer priority and explicit eligibility |
| `calls.call_id`, `call_status`, `agent_id`, `vendor_id`, `duration_sec` | Historical outcome vocabulary and rough duration dimensions | Not causal or a reliable real-time state source; duplicate rows and missing agents |
| `call_attempts.attempt_id`, `attempt_no`, `attempt_status` | Attempt/retry concepts | Missing provider links and repeated event references; prototype retry policy is independent |
| `call_dispositions.disposition_code` | Potential future outcome taxonomy | Legacy codes require canonicalization before use |
| `vendor_telephony.vendor_id`, `status`, `schema_version` | Provider entity vocabulary | Historical vendor status is not provider health; real names/accounts are not used |
| `complaints`, `payments`, `promises_to_pay`, `account_status_history` | Future synthetic eligibility/exclusion scenarios | Should not be used for dialer decisions before policy validation; histories contain duplicates/conflicts |
| `sms_events`, `whatsapp_events`, `field_visits` | Explicitly outside voice simulation scope | Other channels and location data are unnecessary for this prototype |

The simulator currently uses the `borrowers` and `agents` concepts only, with synthetic IDs generated in memory, plus separate simulated call attempts and provider events. A real implementation would need validated consent/suppression rules, jurisdictional contact windows, identity and deduplication policy, and audited current presence inputs.
