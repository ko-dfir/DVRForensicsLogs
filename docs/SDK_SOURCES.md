# SDK and log interpretation sources

## TVT

Manufacturer-authored files mirrored in the independent
[2BAD/tvt repository](https://github.com/2BAD/tvt):

- [dvrdvstypedef.h](https://github.com/2BAD/tvt/blob/master/docs/vendor/include/dvrdvstypedef.h):
  N9000_LOG_TYPE and N9000_LOG_MAJOR_TYPE.
- [DD_LOG_INFO](https://github.com/2BAD/tvt/blob/master/docs/vendor/html/interface/struct/DD_LOG_INFO.htm):
  named log operations, account/address/time and information fields.
- [NET_SDK_LOG](https://github.com/2BAD/tvt/blob/master/docs/vendor/html/interface/struct/NET_SDK_LOG.htm):
  the live SDK log result structure.
- [Manufacturer download center](https://www.tvt.net.cn/download/index1193.html).

`scripts/tvt_sdk_types.py` implements all 38 N9000 types and 24 named operations
from DD_LOG_INFO. If a copy of the header is placed at
`scratchpad/tvt_headers/dvrdvstypedef.h`, a unit test compares the enum against
it; otherwise that check is skipped.
This does not establish that raw disk `action:N` uses the N9000 numeric space.
Only named macros or explicitly identified `sdk_log_type`/`n9000_type` fields
are resolved through that enum. Unknown raw numeric actions stay unchanged;
the original seven raw-image mappings are retained separately.

## Dahua

- [Dahua NetSDK mirror (452/dahua-sdk)](https://github.com/452/dahua-sdk).
- Dahua *NetSDK Programming Guide* and *NetSDK Python Programming Manual*
  (not bundled).
- [Published DVR study](https://doi.org/10.1111/1556-4029.15401) and
  [thesis, Appendix A](https://dione.lib.unipi.gr/xmlui/handle/unipi/15806):
  on-disk vocabulary and the basis of the existing event interpretation.

On-disk SQLite JSON is not asserted to be the live NetSDK LOG_ITEM structure.
The new field explanations retain original values and mark unknown meanings.
An EventAction from SQLite is not equated with a live SDK nEventAction.
Some event types may exist only in the recorder, not its disk databases.

## Hikvision

- Manufacturer *Device Network SDK (General) Developer Guide*, "HCNetSDK Log
  Types" appendix (not bundled).
- `scripts/hikvision_log_types.json` retains the SDK-derived major/minor mapping.
  The RATS layout, disk offsets and payload locations come from the existing
  reverse engineering and validation, not the live-device SDK definition.

See the brand-specific forensic documents for further context. SDK licensing
and redistribution terms remain separate from the source project.
