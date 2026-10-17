import os
import sqlite3
import argparse
import csv
import json
import base64
import html as html_lib
import mimetypes
import struct
import re
import zlib
from collections import Counter
from datetime import datetime
from pathlib import Path

from scripts.display_values import display_value
from scripts.tvt_log_fields import ensure_tvt_mlogtype

# Import our engines
from scripts.engine_hikvision import HikvisionEngine
from scripts.engine_dahua import DahuaEngine
from scripts.engine_tvt import TVTEngine
from scripts.engine_icatch import detect_icatch_structure
from scripts.image_io import open_image
from scripts.physical_drive import is_physical_drive


def _open_image(image_path):
    """Open raw and E01 images through the same seek/read interface."""
    return open_image(image_path)


def _media_size(handle, image_path):
    known_size = getattr(handle, "size", None)
    return int(known_size if known_size is not None else os.path.getsize(image_path))


def _read_at(handle, offset, size, media_size):
    if offset < 0 or offset >= media_size:
        return b""
    handle.seek(offset)
    return handle.read(min(size, media_size - offset))


def _dahua_ewf_boot_evidence(image_path):
    """Quickly validate the Dahua GPT layout from the first EWF data chunk.

    Very large monolithic E01 files can take libewf minutes to index. EWF keeps
    the disk's boot block in an early zlib stream, so inspect that structure
    directly without trusting the evidence filename or acquisition case name.
    """
    try:
        with open(image_path, "rb") as source:
            container_head = source.read(4 * 1024 * 1024)
    except OSError:
        return ""
    if not container_head.startswith((b"EVF\x09\x0d\x0a\xff\x00", b"LVF\x09\x0d\x0a\xff\x00")):
        return ""
    for match in re.finditer(b"\x78[\x01\x5e\x9c\xda]", container_head):
        try:
            boot = zlib.decompressobj().decompress(
                container_head[match.start():], 1024 * 1024)
        except zlib.error:
            continue
        gpt_offset = boot.find(b"EFI PART")
        if gpt_offset < 512 or len(boot) < gpt_offset + 92:
            continue
        disk_start = gpt_offset - 512
        header = boot[gpt_offset:gpt_offset + 512]
        entry_lba = struct.unpack("<Q", header[72:80])[0]
        entry_count = min(struct.unpack("<I", header[80:84])[0], 256)
        entry_size = struct.unpack("<I", header[84:88])[0]
        if not (128 <= entry_size <= 4096):
            continue
        entries_offset = disk_start + entry_lba * 512
        for index in range(entry_count):
            start = entries_offset + index * entry_size
            entry = boot[start:start + entry_size]
            if len(entry) < 128 or entry[:16] == b"\x00" * 16:
                continue
            first_lba = struct.unpack("<Q", entry[32:40])[0]
            last_lba = struct.unpack("<Q", entry[40:48])[0]
            name = entry[56:128].decode("utf-16le", "ignore").rstrip("\x00")
            size_gib = (last_lba - first_lba + 1) * 512 / (1024 ** 3)
            if name.lower() == "msftdata" and 8 <= size_gib <= 12:
                return (f"Dahua-style terminal GPT partition '{name}' "
                        f"({size_gib:.1f} GiB) at LBA {first_lba}")
    return ""


def detect_brand_details(image_path):
    """Detect a DVR family from on-media structures, never from its filename.

    The signatures and probe regions are based on the validated images in the
    project's testing ground.  A generic GPT is deliberately not enough for a
    Dahua result and an unsigned image is UNKNOWN rather than assumed to be TVT.
    """
    if not is_physical_drive(image_path) and not os.path.isfile(image_path):
        raise FileNotFoundError(image_path)

    scores = {"DAHUA": 0, "HIKVISION": 0, "TVT": 0, "ICATCH": 0}
    evidence = {"DAHUA": [], "HIKVISION": [], "TVT": [], "ICATCH": []}

    if image_path.lower().endswith((".e01", ".ex01")):
        fast_dahua = _dahua_ewf_boot_evidence(image_path)
        if fast_dahua:
            return {
                "brand": "DAHUA", "confidence": "MEDIUM", "score": 70,
                "reason": fast_dahua,
                "evidence": [fast_dahua],
                "scores": {"DAHUA": 70, "HIKVISION": 0, "TVT": 0},
            }

    with _open_image(image_path) as image:
        size = _media_size(image, image_path)
        head = _read_at(image, 0, 16 * 1024 * 1024, size)

        hik_pos = head.find(b"HIKVISION@HANGZHOU")
        if hik_pos >= 0:
            scores["HIKVISION"] += 100
            evidence["HIKVISION"].append(
                f"HIKVISION@HANGZHOU filesystem header at 0x{hik_pos:x}")

        rats_count = head.count(b"RATS")
        if rats_count >= 3:
            scores["HIKVISION"] += 70
            evidence["HIKVISION"].append(
                f"{rats_count} RATS log signatures in the initial 16 MiB")

        icatch = detect_icatch_structure(head)
        if icatch:
            scores["ICATCH"] += 100
            evidence["ICATCH"].append(
                f"Validated {icatch['entries']} fixed-cadence HOUR index records "
                f"from 0x{icatch['offset']:x}")

        # Dahua validation: GPT plus an actual XFS superblock at a partition
        # boundary. GPT or a partition name alone is not vendor-specific.
        gpt = _read_at(image, 512, 512, size)
        if gpt[:8] == b"EFI PART" and len(gpt) >= 92:
            entry_lba = struct.unpack("<Q", gpt[72:80])[0]
            entry_count = min(struct.unpack("<I", gpt[80:84])[0], 256)
            entry_size = struct.unpack("<I", gpt[84:88])[0]
            if 128 <= entry_size <= 4096:
                entries = _read_at(
                    image, entry_lba * 512, entry_count * entry_size, size)
                for index in range(entry_count):
                    entry = entries[index * entry_size:(index + 1) * entry_size]
                    if len(entry) < 128 or entry[:16] == b"\x00" * 16:
                        continue
                    first_lba = struct.unpack("<Q", entry[32:40])[0]
                    name = entry[56:128].decode("utf-16le", "ignore").rstrip("\x00")
                    magic = _read_at(image, first_lba * 512, 4, size)
                    if magic == b"XFSB":
                        scores["DAHUA"] += 100
                        evidence["DAHUA"].append(
                            f"GPT partition '{name or index}' has XFSB at LBA {first_lba}")
                        break

        # TVT logs are sequestered around the 1 GB physical region. Probe it
        # directly so a headless TVT disk is identified positively rather than
        # by being neither Dahua nor Hikvision.
        if max(scores.values()) < 100:
            mib = 1024 * 1024
            for probe_mib in (900, 940, 980, 1020, 1060):
                data = _read_at(image, probe_mib * mib, 16 * mib, size)
                pos = data.find(b"mlogtype:")
                if pos >= 0:
                    absolute = probe_mib * mib + pos
                    scores["TVT"] += 100
                    evidence["TVT"].append(
                        f"mlogtype payload at 0x{absolute:x} (~{absolute / mib:.1f} MiB)")
                    break

        # Useful for extracted standalone TVT chunks as well as full images.
        if b"mlogtype:" in head:
            pos = head.find(b"mlogtype:")
            scores["TVT"] += 100
            evidence["TVT"].append(f"mlogtype payload at 0x{pos:x}")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    brand, score = ranked[0]
    tied = len(ranked) > 1 and ranked[1][1] == score
    if score < 60 or tied:
        return {
            "brand": "UNKNOWN", "confidence": "NONE", "score": score,
            "reason": "No unique validated DVR signature was found.",
            "evidence": [], "scores": scores,
        }
    confidence = "HIGH" if score >= 100 else "MEDIUM"
    return {
        "brand": brand, "confidence": confidence, "score": score,
        "reason": "; ".join(evidence[brand]),
        "evidence": evidence[brand], "scores": scores,
    }

def detect_brand(image_path):
    """
    Heuristic detection of the DVR brand based on disk structures.
    Returns: 'DAHUA', 'HIKVISION', 'TVT', or 'UNKNOWN'
    """
    print("[*] Analyzing on-media signatures to detect DVR brand...")
    result = detect_brand_details(image_path)
    print(f"[+] Detection: {result['brand']} ({result['confidence']}) - {result['reason']}")
    return result["brand"]

def _quoted_identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


def _report_logo_data_uri(logo_path):
    if not logo_path or not os.path.isfile(logo_path):
        return ""
    mime = mimetypes.guess_type(logo_path)[0] or "image/png"
    with open(logo_path, "rb") as logo_file:
        payload = base64.b64encode(logo_file.read()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def export_to_html(db_path, table_name, out_html, where="", params=None,
                   logo_path="", report_context=None):
    """Write bounded, linked HTML pages rather than one enormous document."""
    context = report_context or {}
    page_size = max(10, min(1000, int(context.get("page_size", 100))))
    target = Path(out_html)
    target.parent.mkdir(parents=True, exist_ok=True)
    index_path = target.with_name(f"{target.stem}_index.js")
    logo_uri = _report_logo_data_uri(logo_path)
    with sqlite3.connect(db_path) as conn:
        if table_name == 'tvt_logs':
            ensure_tvt_mlogtype(conn)
        table = _quoted_identifier(table_name)
        available = [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]
        chosen = context.get('columns')
        if chosen is not None:
            if not isinstance(chosen, (list, tuple)) or not chosen or any(name not in available for name in chosen):
                raise ValueError('Choose at least one valid report column.')
            if len(set(chosen)) != len(chosen):
                raise ValueError('Report columns must be unique.')
        projection = ', '.join(_quoted_identifier(name) for name in chosen) if chosen else '*'
        total_rows = conn.execute(
            f"SELECT count(*) FROM {table}{where}", params or []).fetchone()[0]
        cursor = conn.execute(
            f"SELECT {projection} FROM {table}{where}", params or [])
        columns = [description[0] for description in cursor.description]
        category_column = context.get("category_column")
        if category_column not in columns:
            category_column = next((name for name in (
                "category", "event_category", "major_type") if name in columns), None)
        category_index = columns.index(category_column) if category_column in columns else None
        counts = Counter()
        if category_column:
            category = _quoted_identifier(category_column)
            category_rows = conn.execute(
                f"SELECT {category}, count(*) FROM {table}{where} "
                f"GROUP BY {category}", params or [])
            counts = Counter({str(value): count for value, count in category_rows
                              if value not in (None, "")})
        categories = sorted(counts, key=str.casefold)
        mlogtypes = []
        if 'mlogtype' in columns:
            mlogtypes = [str(row[0]) for row in conn.execute(
                f'SELECT DISTINCT mlogtype FROM {table}{where} ORDER BY mlogtype', params or [])
                if row[0] not in (None, '')]
        total_pages = max(1, (total_rows + page_size - 1) // page_size)
        with index_path.open("w", encoding="utf-8") as index_file:
            index_file.write("window.REPORT_INDEX=[\n")
            first_entry = True
            for page_number in range(1, total_pages + 1):
                page_path = target if page_number == 1 else target.with_name(
                    f"{target.stem}_page_{page_number:04d}{target.suffix}")
                page_rows = cursor.fetchmany(page_size)
                for row_number, row in enumerate(page_rows, 1):
                    category_value = (str(row[category_index])
                                      if category_index is not None and row[category_index] is not None
                                      else "")
                    values = [display_value(column, value)
                              for column, value in zip(columns, row)]
                    entry = [page_number, row_number, category_value, values]
                    index_file.write((",\n" if not first_entry else "") +
                                     json.dumps(entry, ensure_ascii=False))
                    first_entry = False
                page_html = _html_report_page(columns, page_rows, context, logo_uri,
                                              category_index, categories, counts,
                                              table_name, total_rows, page_number,
                                              total_pages, target, mlogtypes)
                page_path.write_text(page_html, encoding="utf-8")
            index_file.write("\n];\n")
    print(f"[+] HTML Report generated: {target} ({total_pages} page(s))")
    return [str(target if number == 1 else target.with_name(
        f"{target.stem}_page_{number:04d}{target.suffix}"))
        for number in range(1, total_pages + 1)] + [str(index_path)]


def _html_report_page(columns, rows, context, logo_uri, category_index,
                      categories, counts, table_name, total_rows, page_number,
                      total_pages, target, mlogtypes=None):
    show_metadata = context.get("show_metadata", True)

    def page_name(number):
        return target.name if number == 1 else f"{target.stem}_page_{number:04d}{target.suffix}"

    html = ["<!doctype html><html><head><meta charset='utf-8'><style>"]
    html.append("""
    :root { --blue:#155eef; --navy:#102a56; --pale:#eef4ff; --line:#c9d8f5; }
    * { box-sizing:border-box; } body { margin:0; color:#17223b; background:#f4f7fc;
      font:14px/1.45 'Segoe UI',Arial,sans-serif; }
    .report { max-width:1500px; margin:24px auto; background:white; box-shadow:0 8px 28px #1232;
      border-radius:14px; overflow:hidden; }
    header { display:flex; align-items:center; gap:20px; padding:26px 32px;
      color:white; background:linear-gradient(120deg,var(--navy),var(--blue)); }
    header img { max-width:180px; max-height:72px; object-fit:contain; background:white;
      border-radius:8px; padding:7px; } h1 { margin:0 0 3px; font-size:25px; }
    .meta { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px;
      padding:18px 32px; background:var(--pale); border-bottom:1px solid var(--line); }
    .meta div { background:white; border:1px solid var(--line); border-radius:8px; padding:10px 12px; }
    .meta b { color:var(--navy); display:block; font-size:11px; text-transform:uppercase; }
    .table-wrap { overflow:auto; padding:20px 32px 32px; }
    table { border-collapse:collapse; width:max-content; min-width:100%; }
    .report-controls { display:flex; align-items:center; gap:10px; flex-wrap:wrap;
      padding:14px 32px 0; color:var(--navy); font-weight:600; }
    .report-controls select, .report-controls input { min-width:150px; padding:7px 10px; border:1px solid var(--line);
      border-radius:7px; background:white; color:var(--navy); }
    .report-controls button { padding:7px 12px; border:1px solid var(--line); border-radius:7px;
      background:var(--pale); color:var(--navy); cursor:pointer; }
    .report-controls button:disabled { opacity:.5; cursor:default; }
    .category-summary { padding:10px 32px 0; color:var(--navy); }
    .category-summary span { display:inline-block; margin:0 6px 5px 0; padding:4px 8px;
      border-radius:12px; background:var(--pale); border:1px solid var(--line); }
    th,td { border:1px solid #dce4f2; padding:8px 10px; text-align:left; vertical-align:top;
      min-width:125px; max-width:460px; white-space:pre-wrap; overflow-wrap:anywhere; }
    th { position:sticky; top:0; color:white; background:var(--blue); }
    tr:nth-child(even) { background:#f6f9ff; } tr:hover { background:#e8f0ff; }
    tr:target { outline:3px solid #f5a623; background:#fff4d8; }
    .page-links { display:flex; gap:10px; align-items:center; padding:12px 32px; }
    .page-links a { color:var(--blue); text-decoration:none; font-weight:600; }
    .global-results { margin:16px 32px 0; padding:12px; border:1px solid var(--line);
      border-radius:8px; background:#f8fbff; }
    .global-results ol { padding-left:28px; margin:8px 0; }
    .global-results li { margin:5px 0; overflow-wrap:anywhere; }
    .global-results a { color:var(--blue); }
    .result-nav { display:flex; gap:12px; align-items:center; }
    footer { padding:12px 32px; color:#60708f; border-top:1px solid var(--line); }
    @media print { .report-controls { display:none; } tr[hidden] { display:table-row !important; } }
    """)
    html.append("</style></head><body><main class='report'><header>")
    if logo_uri:
        html.append(f"<img src='{logo_uri}' alt='Report logo'>")
    html.append(f"<div><h1>{html_lib.escape(str(context.get('title') or 'CCTV Log Analyzer Report'))}</h1>")
    html.append(f"<div>{html_lib.escape(str(context.get('subtitle', 'Filtered evidence export')))}</div></div></header>")
    if show_metadata:
        html.append("<section class='meta'>")
    metadata = {
        "Generated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "Dataset": table_name,
        "Exported records": f"{total_rows:,}",
        **context.get("metadata", {}),
    }
    if show_metadata:
        for key, value in metadata.items():
            html.append(f"<div><b>{html_lib.escape(str(key))}</b>{html_lib.escape(str(value))}</div>")
        html.append("</section>")
    html.append("<div class='report-controls'>")
    mlogtype_index = columns.index('mlogtype') if 'mlogtype' in columns else -1
    if mlogtype_index >= 0:
        html.append("<label for='report-mlogtype'>TVT mlogtype (all pages)</label>")
        html.append("<select id='report-mlogtype'><option value=''>All mlogtypes</option>")
        for value in mlogtypes or []:
            html.append(f"<option value='{html_lib.escape(value, quote=True)}'>{html_lib.escape(value)}</option>")
        html.append('</select>')
    if category_index is not None:
        html.append("<label for='report-category'>Log category (all pages)</label>")
        html.append("<select id='report-category'><option value=''>All categories</option>")
        for category in categories:
            escaped = html_lib.escape(category, quote=True)
            html.append(f"<option value='{escaped}'>{html_lib.escape(category)}</option>")
        html.append("</select>")
    html.append("<label for='report-search'>Search all pages</label><input id='report-search' type='search' placeholder='Search all exported records'>")
    html.append("<span id='visible-count'></span></div>")
    html.append("<section id='global-results' class='global-results' hidden><b>Matching records across all pages</b>")
    html.append("<div class='table-wrap'><table><thead><tr>")
    for column in columns:
        html.append(f"<th>{html_lib.escape(str(column))}</th>")
    html.append("<th>Source page</th></tr></thead><tbody id='result-body'></tbody></table></div>")
    html.append("<div class='result-nav'><button id='result-prev' type='button'>Previous results</button>")
    html.append("<span id='result-page'></span><button id='result-next' type='button'>Next results</button></div></section>")
    if category_index is not None:
        html.append("<div class='category-summary' aria-label='Category counts'>All exported records · ")
        for category, count in counts.items():
            html.append(f"<span>{html_lib.escape(category)}: {count:,}</span>")
        html.append("</div>")
    html.append("<div class='table-wrap'><table><thead><tr>")
    for col in columns:
        html.append(f"<th>{html_lib.escape(str(col))}</th>")
    html.append("</tr></thead><tbody>")
    
    for row_number, row in enumerate(rows, 1):
        mlogtype_attr = (f" data-mlogtype='{html_lib.escape(str(row[mlogtype_index] or ''), quote=True)}'"
                        if mlogtype_index >= 0 else '')
        if category_index is None:
            html.append(f"<tr id='record-{page_number}-{row_number}'{mlogtype_attr}>")
        else:
            value = "" if row[category_index] is None else str(row[category_index])
            html.append(f"<tr id='record-{page_number}-{row_number}' "
                        f"data-category='{html_lib.escape(value, quote=True)}'{mlogtype_attr}>")
        for col, val in zip(columns, row):
            html.append(f"<td>{html_lib.escape(display_value(col, val))}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div><nav class='page-links' aria-label='Report pages'>")
    if page_number > 1:
        html.append(f"<a href='{html_lib.escape(page_name(1), quote=True)}'>First</a>")
        html.append(f"<a href='{html_lib.escape(page_name(page_number - 1), quote=True)}'>Previous</a>")
    html.append(f"<span>Page {page_number:,} of {total_pages:,}</span>")
    if page_number < total_pages:
        html.append(f"<a href='{html_lib.escape(page_name(page_number + 1), quote=True)}'>Next</a>")
        html.append(f"<a href='{html_lib.escape(page_name(total_pages), quote=True)}'>Last</a>")
    html.append("</nav><footer>Generated by CCTV Log Analyzer</footer></main>")
    html.append(f"<script src='{html_lib.escape(target.stem, quote=True)}_index.js'></script>")
    html.append(f"<script>const reportFileStem = {json.dumps(target.stem)}; "
                f"const reportFileSuffix = {json.dumps(target.suffix)}; "
                f"const reportMlogtypeIndex = {mlogtype_index};</script>")
    html.append("""<script>
        const categorySelect = document.getElementById('report-category');
        const mlogtypeSelect = document.getElementById('report-mlogtype');
        const reportSearch = document.getElementById('report-search');
        const reportRows = [...document.querySelectorAll('tbody tr')];
        const visibleCount = document.getElementById('visible-count');
        const resultPanel = document.getElementById('global-results');
        const resultBody = document.getElementById('result-body');
        const resultPage = document.getElementById('result-page');
        const previousResults = document.getElementById('result-prev');
        const nextResults = document.getElementById('result-next');
        const index = window.REPORT_INDEX;
        const queryParams = new URLSearchParams(location.search);
        reportSearch.value = queryParams.get('q') || '';
        if (categorySelect) categorySelect.value = queryParams.get('category') || '';
        if (mlogtypeSelect) mlogtypeSelect.value = queryParams.get('mlogtype') || '';
        let matches = [];
        let resultPageNumber = 1;
        const resultPageSize = 50;
        function reportPageName(number) {
          return number === 1 ? reportFileStem + reportFileSuffix :
            reportFileStem + '_page_' + String(number).padStart(4, '0') + reportFileSuffix;
        }
        function resultUrl(entry) {
          const url = new URL(reportPageName(entry[0]), location.href);
          const query = reportSearch.value.trim();
          const category = categorySelect ? categorySelect.value : '';
          if (query) url.searchParams.set('q', query);
          if (category) url.searchParams.set('category', category);
          if (mlogtypeSelect && mlogtypeSelect.value) url.searchParams.set('mlogtype', mlogtypeSelect.value);
          url.hash = 'record-' + entry[0] + '-' + entry[1];
          return url.href;
        }
        function renderResults() {
          resultBody.replaceChildren();
          const pages = Math.max(1, Math.ceil(matches.length / resultPageSize));
          resultPageNumber = Math.min(Math.max(1, resultPageNumber), pages);
          const start = (resultPageNumber - 1) * resultPageSize;
          for (const entry of matches.slice(start, start + resultPageSize)) {
            const row = document.createElement('tr');
            for (const value of entry[3]) {
              const cell = document.createElement('td');
              cell.textContent = value;
              row.append(cell);
            }
            const sourceCell = document.createElement('td');
            const link = document.createElement('a');
            link.href = resultUrl(entry);
            link.textContent = 'Page ' + entry[0] + ', row ' + entry[1];
            sourceCell.append(link);
            row.append(sourceCell);
            resultBody.append(row);
          }
          resultPage.textContent = 'Results page ' + resultPageNumber + ' of ' + pages;
          previousResults.disabled = resultPageNumber <= 1;
          nextResults.disabled = resultPageNumber >= pages;
        }
        function applyFilters() {
          const selected = categorySelect ? categorySelect.value : '';
          const mlogtype = mlogtypeSelect ? mlogtypeSelect.value : '';
          const query = reportSearch.value.trim().toLocaleLowerCase();
          const active = Boolean(selected || mlogtype || query);
          if (!Array.isArray(index)) {
            visibleCount.textContent = 'Search index missing; keep the report index.js file beside the HTML pages.';
            return;
          }
          matches = active ? index.filter(entry =>
            (!selected || entry[2] === selected) &&
            (!mlogtype || entry[3][reportMlogtypeIndex] === mlogtype) &&
            (!query || entry[3].join(' | ').toLocaleLowerCase().includes(query))) : [];
          resultPageNumber = 1;
          resultPanel.hidden = !active;
          for (const row of reportRows) {
            row.hidden = Boolean(active && ((selected && row.dataset.category !== selected) ||
              (mlogtype && row.dataset.mlogtype !== mlogtype) ||
              (query && !row.textContent.toLocaleLowerCase().includes(query))));
          }
          visibleCount.textContent = active ?
            `${matches.length.toLocaleString()} matching records across all pages` :
            `${index.length.toLocaleString()} exported records`;
          if (active) renderResults();
          for (const link of document.querySelectorAll('.page-links a')) {
            const url = new URL(link.href);
            url.searchParams.delete('q');
            url.searchParams.delete('category');
            url.searchParams.delete('mlogtype');
            if (query) url.searchParams.set('q', reportSearch.value.trim());
            if (selected) url.searchParams.set('category', selected);
            if (mlogtype) url.searchParams.set('mlogtype', mlogtype);
            link.href = url.href;
          }
        }
        if (categorySelect) categorySelect.addEventListener('change', applyFilters);
        if (mlogtypeSelect) mlogtypeSelect.addEventListener('change', applyFilters);
        reportSearch.addEventListener('input', applyFilters);
        previousResults.addEventListener('click', () => { resultPageNumber -= 1; renderResults(); });
        nextResults.addEventListener('click', () => { resultPageNumber += 1; renderResults(); });
        applyFilters();
        </script>""")
    html.append("</body></html>")
    return "\n".join(html)

def export_to_csv(db_path, table_name, out_csv, where="", params=None):
    conn = sqlite3.connect(db_path)
    if table_name == 'tvt_logs':
        ensure_tvt_mlogtype(conn)
    c = conn.cursor()
    c.execute(f"SELECT * FROM {_quoted_identifier(table_name)}{where}", params or [])
    
    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f: # utf-8-sig for Excel compatibility
        writer = csv.writer(f)
        columns = [d[0] for d in c.description]
        writer.writerow(columns)
        for row in c:
            writer.writerow([display_value(column, value)
                             for column, value in zip(columns, row)])
        
    conn.close()
    print(f"[+] CSV/Excel Report generated: {out_csv}")

def main():
    parser = argparse.ArgumentParser(description="CCTV Log Analyzer extractor")
    parser.add_argument("image", help="Path to the E01 or DD image file")
    parser.add_argument("--out", default="./output", help="Output directory for databases and reports")
    parser.add_argument("--format", choices=['html', 'csv', 'both'], default='both', help="Export format")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.image):
        print(f"[!] File not found: {args.image}")
        return
        
    os.makedirs(args.out, exist_ok=True)
    
    brand = detect_brand(args.image)
    print(f"[+] Detected Brand: {brand}")
    
    db_out_path = os.path.join(args.out, f"Extracted_Logs_{brand}.db")
    
    if brand == 'TVT':
        print("[*] Initializing TVT Engine...")
        engine = TVTEngine(args.image)
        # Limit bytes to 1GB for fast scanning in this demo CLI
        records = engine.extract_logs(limit_bytes=1024*1024*1024)
        engine.save_to_sqlite(records, db_out_path)
        table_name = "tvt_logs"
        
    elif brand == 'DAHUA':
        print("[*] Initializing Dahua Engine...")
        engine = DahuaEngine(args.image)
        partitions = engine.detect_partitions()
        xfs_part = next((p for p in partitions if p['is_target']), None)
        if xfs_part:
            print(f"[*] Extracting Native XFS Physical Databases...")
            extracted = engine.extract_xfs_native(xfs_part['start_lba'] * 512, args.out)
            # For Dahua, the DB is already extracted by dissect.xfs
            if extracted:
                db_out_path = extracted[0] # Just take the first one for reporting
                table_name = "log" # Dahua internal table name is usually 'log' or 'syslog'
        
    elif brand == 'HIKVISION':
        print("[*] Initializing Hikvision Engine...")
        engine = HikvisionEngine(args.image)
        # Assuming HikvisionEngine has a carve_to_sqlite method
        engine.carve_to_sqlite(db_out_path)
        table_name = "hikvision_logs"
    
    # Reports
    if os.path.exists(db_out_path):
        print("[*] Generating reports...")
        base_name = os.path.splitext(db_out_path)[0]
        
        # Check if table exists (in case Dahua db name differs)
        conn = sqlite3.connect(db_out_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in c.fetchall() if t[0] != 'sqlite_sequence']
        conn.close()
        
        if tables:
            target_table = next(
                (name for name in ('log', 'syslog', 'hikvision_logs', 'tvt_logs')
                 if name in tables),
                tables[0],
            )
            if args.format in ['csv', 'both']:
                export_to_csv(db_out_path, target_table, f"{base_name}_Report.csv")
            if args.format in ['html', 'both']:
                export_to_html(db_out_path, target_table, f"{base_name}_Report.html")
        else:
            print("[!] No tables found in the database to export.")

if __name__ == "__main__":
    main()
