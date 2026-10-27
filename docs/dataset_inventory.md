# Dataset inventory

Source directory: `data/raw/collections_30k_dataset/`. Its README labels the 17 relational tables as synthetic collections analytics, seed 42, and notes duplicates, nulls, inconsistent identifiers, mixed UTC/Asia/Kolkata/Asia/Dubai timestamps, late events, schema versions, legacy codes, and conflicting histories. The extracted CSVs are locally available; no ZIP was found in the workspace. Raw data is ignored by Git and remains unmodified. This report contains counts and schemas only.

| Table | Rows | Columns |
|---|---:|---:|
| accounts | 30,000 | 11 |
| account_status_history | 60,000 | 8 |
| agents | 30,000 | 8 |
| agent_sessions | 15,000 | 7 |
| borrowers | 30,600 | 8 |
| calls | 91,350 | 11 |
| call_attempts | 120,000 | 9 |
| call_dispositions | 35,000 | 8 |
| campaigns | 120 | 7 |
| complaints | 8,000 | 9 |
| daily_targeting | 45,000 | 7 |
| field_visits | 25,000 | 10 |
| payments | 25,500 | 9 |
| promises_to_pay | 18,000 | 9 |
| sms_events | 45,000 | 8 |
| vendor_telephony | 15 | 6 |
| whatsapp_events | 60,600 | 8 |
| data_dictionary | 143 | 3 |

Total: 639,328 data rows including the dictionary. The CSV headers and field types are described in the supplied `data_dictionary.csv`. No table is automatically loaded into the simulator.
