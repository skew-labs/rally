"""Build the public algorithm catalog from official logo assets and factor files.

Run on the authorized remote host. Raw research files stay in the evidence directory;
only dated summary statistics and normalized marks enter the public catalog.
"""
import argparse
import calendar
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
import openpyxl


def trailing_year(rows):
    """Require twelve consecutive complete monthly observations, never annualize a sample."""
    ordered = sorted(rows)[-12:]
    if len(ordered) != 12 or any(not math.isfinite(v) or v <= -1 for _, v in ordered):
        raise ValueError('A complete finite year is required')
    months = [d.year * 12 + d.month for d, _ in ordered]
    if months != list(range(months[0], months[0] + 12)):
        raise ValueError('Missing month in the return series')
    return (math.prod(1 + v for _, v in ordered) - 1) * 100, ordered


def factor(path, sheet, column):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(workbook[sheet].values)
    header = next(row for row in rows if column in row and ('DATE' in row or 'TSMOM' in row))
    index = header.index(column)
    observations = []
    for row in rows:
        date = row[0]
        if isinstance(date, str):
            try:
                date = datetime.strptime(date, '%m/%d/%Y')
            except ValueError:
                continue
        if isinstance(date, datetime) and isinstance(row[index], (float, int)):
            observations.append((date, row[index]))
    result, window = trailing_year(observations)
    end = window[-1][0]
    return {
        'returnPct': round(result, 6), 'months': 12, 'basis': 'published_factor',
        'from': window[0][0].replace(day=1).date().isoformat(),
        'to': end.replace(day=calendar.monthrange(end.year, end.month)[1]).date().isoformat(),
        'series': column, 'sheet': sheet, 'feesIncluded': False, 'excessReturn': True,
        'sourceSHA256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'checkedAt': datetime.now(timezone.utc).isoformat(),
    }


def mark(path, dark=False):
    image = Image.open(path).convert('RGBA')
    pixels = image.load()
    # Remove only the edge-connected, near-white canvas added by the old normalizer.
    seen = set()
    stack = [(x, y) for x in range(image.width) for y in (0, image.height - 1)]
    stack += [(x, y) for y in range(image.height) for x in (0, image.width - 1)]
    while stack:
        x, y = stack.pop()
        if (x, y) in seen or x < 0 or y < 0 or x >= image.width or y >= image.height:
            continue
        seen.add((x, y))
        r, g, b, alpha = pixels[x, y]
        if alpha < 10 or min(r, g, b) >= 243:
            pixels[x, y] = (r, g, b, 0)
            stack.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    bbox = image.getchannel('A').getbbox()
    if not bbox:
        raise ValueError('Empty official logo')
    image = image.crop(bbox)
    visible = [p for p in image.getdata() if p[3] > 64]
    monochrome = sum(max(p[:3]) - min(p[:3]) < 16 and max(p[:3]) < 125 for p in visible) / len(visible) > .9
    if dark and monochrome:
        image.putdata([(235, 236, 241, p[3]) if p[3] else p for p in image.getdata()])
    image.thumbnail((144, 144), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (160, 160))
    canvas.alpha_composite(image, ((160 - image.width) // 2, (160 - image.height) // 2))
    output = io.BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    return output.getvalue()


def build(root, evidence):
    from_url = (root / 'assets/algorithm-library-data.js').read_text().split('"')[1]
    data = json.loads((root / from_url.lstrip('/')).read_text())
    icons = {}
    for source in data['sources']:
        original = root / source['logo'].lstrip('/')
        light_raw = mark(original)
        for dark in (False, True):
            raw = mark(original, dark) if dark else light_raw
            suffix = '-dark' if dark and raw != light_raw else ''
            name = f"algorithm-brand-{source['id']}{suffix}-{hashlib.sha256(raw).hexdigest()[:16]}.png"
            (root / 'assets' / name).write_bytes(raw)
            source['logoDark' if dark else 'logo'] = '/assets/' + name
        icons[source['id']] = source
    datasets = [
        ('001', 'Time-Series-Momentum-Factors-Monthly', 'TSMOM Factors', 'TSMOM', 'Global multi-asset', 'time-series-momentum-factors-monthly'),
        ('002', 'Value-and-Momentum-Everywhere-Factors-Monthly', 'VME Factors', 'MOMLS_VME_US90', 'U.S. equities', 'value-and-momentum-everywhere-factors-monthly'),
        ('003', 'Value-and-Momentum-Everywhere-Factors-Monthly', 'VME Factors', 'VALLS_VME_US90', 'U.S. equities', 'value-and-momentum-everywhere-factors-monthly'),
        ('004', 'Quality-Minus-Junk-Factors-Monthly', 'QMJ Factors', 'Global', 'Global equities', 'quality-minus-junk-factors-monthly'),
        ('005', 'Betting-Against-Beta-Equity-Factors-Monthly', 'BAB Factors', 'Global', 'Global equities', 'betting-against-beta-equity-factors-monthly'),
    ]
    performance = {}
    for number, stem, sheet, column, universe, slug in datasets:
        path = evidence / 'factors' / (stem + '.xlsx')
        record = factor(path, sheet, column)
        record.update(universe=universe, sourceURL='https://www.aqr.com/Insights/Datasets/' + slug,
                      downloadURL='https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/' + stem + '.xlsx')
        performance['rally-ref-' + number] = record
    for item in data['items']:
        source = icons.get(item.get('sourceId'))
        if source:
            item.update(brandIcon=source['logo'], brandIconDark=source['logoDark'])
        item['performance1Y'] = performance.get(item['id'])
    data['performanceCheckedOn'] = datetime.now(timezone.utc).date().isoformat()
    encoded = (json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    url = '/assets/algorithm-library-' + hashlib.sha256(encoded).hexdigest()[:16] + '.json'
    (root / url.lstrip('/')).write_bytes(encoded)
    (root / 'assets/algorithm-library-data.js').write_text('export const ALGORITHM_LIBRARY_URL="' + url + '";\n')
    (root / 'android/app/src/main/java/com/rallydot/app/AlgorithmLibraryConfig.kt').write_text(
        'package com.rallydot.app\nconst val ALGORITHM_LIBRARY_URL="' + url + '"\n')
    (evidence / 'performance-summary.json').write_text(json.dumps(performance, indent=2))
    print(json.dumps({'catalog': url, 'officialMarks': len(icons), 'completeYears': len(performance)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    build(args.root, args.evidence)
