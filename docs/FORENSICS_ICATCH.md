# iCatch forensic notes

The validated 1.86 TiB raw image has no conventional MBR/GPT partition table.
Bounded Shannon-entropy profiling showed a structured metadata area in the
first 8 MiB and high-entropy video data after it. Entropy is used only to find
candidate regions; it is not treated as proof of a log format.

At offset `0x400000`, the image contains 324-byte (`0x144`) records with
`HOUR_...` keys. Each accepted record must satisfy all of the following:

- the key has the validated `HOUR_[0-9]{5}:HH` structure;
- the embedded Unix timestamp is plausible and its hour agrees with the key;
- adjacent records are exactly `0x144` bytes apart;
- adjacent timestamps advance by exactly 3,600 seconds.

The sample contains 898 records satisfying every condition (about 37 days of
consecutive hourly entries). These entries are a
recording timeline/index, not an audit trail of logins or configuration events.
The engine intentionally labels them as `icatch_timeline` and does not infer
event meanings that are not present on disk.

The desktop workbench reports **No user logs found** for the analyzed ICATCH
image and disables Carve Data for this brand. The recording timeline remains
documented here but is not shown as a user-log result.

A full-address-space hierarchical entropy/signature survey is documented in
`ICATCH1_MEDIA_SURVEY.md`. It found no second structurally valid audit-log area;
apparent short text/filesystem signatures in high-entropy video were rejected
as false positives.
