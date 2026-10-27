# Aggregate data profile

Profiled locally from the extracted CSVs. The profile intentionally excludes names, contact details, raw identifiers, and row-level samples.

| Table | Missing fields/counts | Exact duplicate rows | Repeated identifier counts (selected) |
|---|---|---:|---|
| borrowers | phone 614; email 895 | 600 | borrower_id 19,585 extra occurrences |
| accounts | borrower_id 455 | 0 | borrower_id 18,602 extra occurrences |
| agents | none | 0 | agent_id 29,000 extra occurrences |
| agent_sessions | none | 0 | agent_id 14,000; device_id 13,500 |
| calls | agent_id 1,827 | 1,271 | call_id 1,350; account_id 62,942 |
| call_attempts | vendor_id 2,400 | 0 | call_id 53,756; agent_id 119,000 |
| call_dispositions | none | 0 | agent_id 34,000; call_id 6,029 |
| daily_targeting | none | 0 | account_id 21,656 |
| complaints | none | 0 | account_id 966 |
| field_visits | scheduled_at 250 | 0 | account_id 8,092 |
| payments | payment_reference 382 | 486 | payment_id 500; payment_reference 4,297 |
| promises_to_pay | none | 0 | account_id 4,468 |
| sms_events | none | 0 | message_id 17,999 |
| whatsapp_events | none | 600 | whatsapp_event_id 600; message_id 25,769 |

The repeated-key figures are extra occurrences beyond the first, not counts of distinct duplicate keys. Entity keys repeat naturally in many event tables, so they are not by themselves evidence of bad events. Exact duplicate rows were counted across all columns. The README flags mixed time zones and conflicting/late timestamps; timezone and temporal ordering would need normalization and business rules before analytical use. Statuses include multiple terminal, intermediate, and legacy-looking values; no status was treated as a real-time agent presence signal.

Data validation caveats: no original assignment PDF was found to define canonical keys or accepted status taxonomies. This initial pass inventories nulls and exact duplicates and selected repeated IDs; it does not establish referential integrity for every relationship or normalize timestamp semantics. Never use names, phone numbers, emails, or raw rows in simulator logs or reports.
