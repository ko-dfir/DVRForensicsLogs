# ICATCH1 whole-address-space media survey

Image: `ICATCH1.001`  
Size: 2,000,398,934,016 bytes (1.86 TiB)

## Method

The survey covered the complete image address range at 1 GiB intervals, using
four 64 KiB probes at relative offsets 0, 4 MiB, 16 MiB and 64 MiB in each
interval. It produced 7,455 entropy/signature samples. Candidate regions were
ranked by entropy and structural signatures; the strongest 68 candidates were
expanded into 67 deep-read ranges of up to 16 MiB.

This is a whole-address-space hierarchical survey, not a byte-for-byte read of
all 1.86 TiB. It is designed to locate metadata islands efficiently in a
very large image.

## Results

- Median sampled entropy: 7.9502 bits/byte, consistent with encoded video.
- The structured initial range `0x0–0xC00000` has entropy 3.5139 and contains
  915 raw `HOUR_...` signatures. Strict cadence/timestamp validation accepts
  898 hourly recording-index records.
- The final 9,527,296 bytes are partly zero/unallocated (entropy 4.3964) and
  contain no coherent log strings or validated records.
- Other apparent `log`, JSON, EXT and XFS strings occur inside high-entropy
  ranges without filesystem alignment, coherent headers, timestamps or record
  cadence. They are random/video-codec false positives, not log evidence.
- No second structured audit-log area (login, user action, configuration or
  alarm database) was identified by this survey.

## Interpretation

Entropy successfully located the recording metadata island but is not itself
evidence of a log. Only the initial hourly index passes structural validation.
A literal sequential byte scan of a 1.86 TiB source is an hours-long operation;
the Entropy test's full-image mode covers every byte with progress and
cancellation.
