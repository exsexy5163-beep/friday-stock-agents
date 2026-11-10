#!/usr/bin/env python3
"""portfolio-risk — สร้าง HTML ธีมมืดแบบสมหมาย (ไฟล์เดียว · ไม่มี JavaScript · ไม่โหลดอะไรจากเน็ต).

รับ dict `c` จาก optimize.run() แล้วจัดหน้าเท่านั้น — ไม่คิดเลขใหม่
สีของทุกช่องในตารางความเสี่ยงมาจาก risk.heat_color() ตัวเดียว
"""
from __future__ import annotations

import html
import math

import risk as rk
from risk import num, pct

MODE_LABEL = {"optimize": "พอร์ตที่คำนวณ", "evaluate": "พอร์ตปัจจุบัน"}

CSS = """
:root{--bg:#0E141A;--card:#161F28;--card2:#1B2631;--ink:#E6E1D6;--mute:#8E9AA6;--line:#26323E;
--gold:#C9A86A;--teal:#5C9FB0;--accent:#C9A86A;--s1:#C9A86A;--s2:#8E9AA6;--s3:#5C9FB0;--warn:#C97A3A;--bad:#A8392F}
*{box-sizing:border-box}html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Sukhumvit Set","Noto Sans Thai",system-ui,sans-serif}
main{max-width:1000px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:24px;margin:0 0 4px;color:var(--gold);letter-spacing:.2px}
h2{font-size:17px;margin:0 0 12px;color:var(--ink)}h2 .no{color:var(--gold);font-variant-numeric:tabular-nums;margin-right:8px}
h3{font-size:15px;margin:0 0 6px}
.sub{color:var(--mute);margin:0 0 18px;font-size:13px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin:0 0 16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.kpi span{display:block;color:var(--mute);font-size:12px}.kpi b{display:block;font-size:20px;font-variant-numeric:tabular-nums}
.kpi i{display:block;font-style:normal;color:var(--mute);font-size:12px;line-height:1.45;margin-top:4px}
.truth{border:1px solid var(--gold);border-left:4px solid var(--gold);background:var(--card2);border-radius:8px;padding:12px 16px;margin:0 0 16px}
.truth h2{color:var(--gold)}.truth ul{margin:0;padding-left:20px}.truth li{margin:3px 0}
.tbl{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--mute);font-weight:600;font-size:12px}
td.h{color:#fff;text-align:center;font-weight:600}td.h.na{color:var(--mute);font-weight:400}
tr.port td{border-top:2px solid var(--gold)}
.bar{height:8px;border-radius:4px;background:var(--gold)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
svg{width:100%;height:auto}.lab{fill:var(--mute);font-size:11px}.val{fill:#fff;font-size:11px}.grid{stroke:var(--line)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--mute);margin-top:4px}
.key i{display:inline-block;width:12px;height:3px;margin-right:6px;vertical-align:middle}
.note{color:var(--mute);font-size:13px}.explain{color:var(--ink);font-size:13px;background:var(--card2);border-radius:6px;padding:8px 10px;margin:10px 0 0}
.flag{color:var(--warn);font-weight:600}.bad{color:#E07A6E;font-weight:600}
.chip{display:inline-block;padding:1px 8px;border-radius:10px;color:#fff;font-size:12px}
.act-up{color:#7FC8A0}.act-down{color:#E0A36E}.act-hold{color:var(--mute)}
dl.gloss{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:6px 14px;margin:0}
dl.gloss dt{color:var(--gold);font-weight:600}dl.gloss dd{margin:0}
ul{padding-left:20px}
@media (max-width:560px){dl.gloss{grid-template-columns:1fr}dl.gloss dd{margin-bottom:8px}}
"""

GLOSSARY = [
    ("β (เบต้า)", "หุ้นขยับแรงแค่ไหนเมื่อเทียบกับตลาด · 1 = ขยับเท่าตลาด · 1.5 = ตลาดขึ้นลง 1% หุ้นมักขยับ 1.5% · ต่ำกว่า 1 = นิ่งกว่าตลาด"),
    ("ความผันผวน (σ)", "ผลตอบแทนแกว่งขึ้นลงมากแค่ไหนต่อปี · ตัวเลขยิ่งสูง ยิ่งมีปีที่ขึ้นแรงและลงแรง"),
    ("correlation", "หุ้นสองตัวขยับไปทางเดียวกันแค่ไหน · 1 = พร้อมกันเป๊ะ · 0 = ไม่เกี่ยวกัน · ติดลบ = สวนทาง · ถือตัวที่ correlation ต่ำด้วยกัน การกระจายถึงจะช่วย"),
    ("หุ้นหลัก", "หุ้นที่น้ำหนักมากสุดในพอร์ต ใช้เป็นแกนเทียบ correlation · ถ้าน้ำหนักเสมอกันหลายตัว ใช้ดัชนีตลาดเป็นแกนแทน"),
    ("Drawdown / ร่วงสูงสุด", "ลงจากจุดสูงสุดก่อนหน้ามากแค่ไหน · −30% = เงิน 100 บาทที่ยอดเหลือ 70 บาท"),
    ("Stress test", "ย้อนดูว่าถ้าถือพอร์ตนี้ในช่วงวิกฤตจริงในอดีต (โควิด 2020 · ดอกเบี้ยขึ้น 2022) จะเจ็บแค่ไหน · ไม่ใช่การพยากรณ์"),
    ("ความเสี่ยงเป็นระบบ", "ส่วนที่ขยับตามตลาดทั้งก้อน (เศรษฐกิจ ดอกเบี้ย สงคราม) · กระจายหุ้นเท่าไรก็ไม่หาย"),
    ("ความเสี่ยงไม่เป็นระบบ", "ส่วนที่มาจากเรื่องของบริษัทเอง (ข่าวร้าย ผู้บริหาร คดี) · ลดได้ด้วยการกระจายหุ้น"),
    ("CAPM", "สูตรที่บอกว่าหุ้นควรให้ผลตอบแทนเท่าไรจาก β: ผลตอบแทนไร้ความเสี่ยง + β × ส่วนเกินของตลาด"),
    ("E(rp)", "ผลตอบแทนคาดหวังต่อปีของพอร์ตตาม CAPM — ค่าตามทฤษฎี ไม่ใช่คำสัญญา"),
    ("r_RF", "ผลตอบแทนไร้ความเสี่ยง ใช้ดอกเบี้ยตั๋วเงินคลังสหรัฐ 3 เดือน"),
    ("r_M", "ผลตอบแทนเฉลี่ยของตลาดหุ้นทั้งตลาด ใช้ค่าเฉลี่ยทบต้นของ SPY ย้อน 20 ปี"),
    ("มูลค่าซื้อขายต่อวัน", "ราคา × จำนวนหุ้นที่ซื้อขายเฉลี่ยต่อวันย้อน 3 เดือน · ยิ่งต่ำ ยิ่งขายออกยากตอนต้องการเงินด่วน"),
    ("จำนวนหุ้นเทียบเท่า", "พอร์ตนี้กระจายเท่ากับถือหุ้นน้ำหนักเท่ากันกี่ตัว · ถือ 10 ตัวแต่ตัวเดียว 80% จะได้ราว 1.5 ตัว"),
    ("heat map", "ตารางระบายสีตามระดับความเสี่ยง 1 (เขียวเข้ม) ถึง 5 (แดง) · ช่องเทา = ข้อมูลไม่พอ ไม่ได้แปลว่าปลอดภัย"),
    ("เพดานเตือน", "หุ้นตัวเดียวตั้งแต่ 20% = เตือน · ตั้งแต่ 30% = เตือนแรง · เป็นแค่สัญญาณให้รู้ตัว ไม่ใช่กฎบังคับ"),
    ("in-sample", "ใช้ข้อมูลชุดเดียวกันทั้งหาคำตอบและวัดผล · ผลจึงดูดีกว่าความจริงในอนาคตได้"),
    ("ปรับพอร์ต (rebalance)", "เทียบสัดส่วนที่ถืออยู่กับสัดส่วนที่ตัวหาน้ำหนักคำนวณ · ห่างเกิน 2 จุด% ถึงนับว่าต่าง"),
    ("อุตสาหกรรม (sector)", "กลุ่มธุรกิจตามการจัดของ Nasdaq (ไม่ใช่มาตรฐาน GICS) · หุ้นกลุ่มเดียวกันมักโดนข่าวเดียวกัน · กองทุน ETF จัดเป็น \"ETF / ไม่ทราบ\" เพราะยังไม่ได้ดูไส้ใน"),
    ("เพดานรายอุตสาหกรรม", "กลุ่มเดียวตั้งแต่ 35% = เตือน · ตั้งแต่ 45% = เตือนแรง · เตือนอย่างเดียว"),
    ("อัตราแลกเปลี่ยน (USD/THB)", "1 ดอลลาร์แลกได้กี่บาท · ตัวเลขลด = บาทแข็ง → หุ้นสหรัฐมีค่าเป็นบาทน้อยลงแม้ราคาในดอลลาร์เท่าเดิม"),
    ("ดอกเบี้ยพันธบัตร 10 ปี (DGS10)", "ผลตอบแทนพันธบัตรรัฐบาลสหรัฐอายุ 10 ปี · เป็นดอกเบี้ยอ้างอิงที่ตลาดใช้คิดมูลค่าหุ้น · ขึ้นแรงมักกดราคาหุ้นเติบโต"),
    ("ดอกเบี้ย +1% หุ้นขยับ", "ในอดีต 3 ปี สัปดาห์ที่ DGS10 ขึ้น 1 จุด% หุ้นมักขยับกี่ % · ติดลบ = หุ้นลงเมื่อดอกเบี้ยขึ้น · เป็นความสัมพันธ์ในอดีต ไม่ใช่กฎตายตัว"),
    ("r² (อาร์สแควร์)", "ดอกเบี้ยอธิบายการขยับของหุ้นได้กี่ส่วน · 0 = ไม่เกี่ยวเลย · 1 = อธิบายได้หมด · ต่ำมาก = ตัวเลขความไวเชื่อถือได้น้อย"),
]


def esc(s) -> str:
    return html.escape(str(s))


def chip(score) -> str:
    if score is None:
        return f"<span class='chip' style='background:{rk.GREY}'>ข้อมูลไม่พอ</span>"
    return f"<span class='chip' style='background:{rk.heat_color(score)}'>{score} · {rk.LEVEL[score]}</span>"


def hcell(cl: dict) -> str:
    if cl.get("anchor"):
        return f"<td class='h na' style='background:{rk.GREY}'>หุ้นหลัก</td>"
    if cl["score"] is None:
        return f"<td class='h na' style='background:{rk.GREY}'>[ข้อมูลไม่พอ]</td>"
    return f"<td class='h' style='background:{rk.heat_color(cl['score'])}'>{esc(cl['text'])}</td>"


def missing(txt="[ข้อมูลไม่พอ]") -> str:
    return f"<span class='flag'>{txt}</span>"


# ================================================================ SVG
def svg_matrix(labels, M, title: str) -> str:
    """เมทริกซ์ correlation · สีช่องจากเกณฑ์ heat map มิติ correlation (แนวทแยงเป็นเทา)."""
    n = len(labels)
    cell, pad = 54, 64
    size = pad + n * cell
    parts = [f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="{esc(title)}">']
    for i, a in enumerate(labels):
        parts.append(f'<text x="{pad - 6}" y="{pad + i * cell + cell / 2 + 4}" text-anchor="end" class="lab">{esc(a)}</text>')
        parts.append(f'<text x="{pad + i * cell + cell / 2}" y="{pad - 8}" text-anchor="middle" class="lab">{esc(a)}</text>')
        for j in range(n):
            v = float(M[i, j])
            col = rk.GREY if i == j else rk.heat_color(rk.heat_score("corr", num(v)))
            parts.append(f'<rect x="{pad + j * cell}" y="{pad + i * cell}" width="{cell - 2}" height="{cell - 2}" '
                         f'rx="4" fill="{col}"><title>{esc(a)} × {esc(labels[j])}: {num(v)}</title></rect>')
            parts.append(f'<text x="{pad + j * cell + cell / 2 - 1}" y="{pad + i * cell + cell / 2 + 4}" '
                         f'text-anchor="middle" class="val">{num(v)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_lines(series, x_labels, y_fmt, marker=None, title="") -> str:
    """series = [(ชื่อ, xs, ys, css-var)] · xs/ys เป็นตัวเลข."""
    W, H, L, R_, T, B = 640, 260, 60, 16, 16, 36
    xs_all = [x for _, xs, _, _ in series for x in xs]
    ys_all = [y for _, _, ys, _ in series for y in ys] + ([marker[1]] if marker else [])
    x0, x1 = min(xs_all), max(xs_all)
    y0, y1 = min(ys_all), max(ys_all)
    if y1 - y0 < 1e-12:
        y0, y1 = y0 - 0.01, y1 + 0.01
    if x1 - x0 < 1e-12:
        x0, x1 = x0 - 1, x1 + 1
    sx = lambda x: L + (x - x0) / (x1 - x0) * (W - L - R_)
    sy = lambda y: T + (y1 - y) / (y1 - y0) * (H - T - B)
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">']
    for k in range(5):
        y = y0 + (y1 - y0) * k / 4
        p.append(f'<line x1="{L}" x2="{W - R_}" y1="{sy(y):.1f}" y2="{sy(y):.1f}" class="grid"/>')
        p.append(f'<text x="{L - 6}" y="{sy(y) + 4:.1f}" text-anchor="end" class="lab">{esc(y_fmt(y))}</text>')
    for x, lab in x_labels:
        anchor = "start" if x <= x0 else "end" if x >= x1 else "middle"   # ป้ายหัว/ท้ายไม่ล้นขอบ
        p.append(f'<text x="{sx(x):.1f}" y="{H - 12}" text-anchor="{anchor}" class="lab">{esc(lab)}</text>')
    for name, xs, ys, col in series:
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys))
        p.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"><title>{esc(name)}</title></polyline>')
    if marker:
        p.append(f'<circle cx="{sx(marker[0]):.1f}" cy="{sy(marker[1]):.1f}" r="5" fill="var(--accent)"><title>{esc(marker[2])}</title></circle>')
    p.append("</svg>")
    legend = "".join(f'<span class="key"><i style="background:{c}"></i>{esc(nm)}</span>' for nm, _, _, c in series)
    return "".join(p) + f'<div class="legend">{legend}</div>'


# ================================================================ ส่วนย่อย
def sec(no: str, title: str, body: str) -> str:
    return f"<section><h2><span class='no'>{no}</span>{esc(title)}</h2>{body}</section>"


def kpi(label, value, note="") -> str:
    return f"<div class='kpi'><span>{esc(label)}</span><b>{value}</b>{f'<i>{esc(note)}</i>' if note else ''}</div>"


def truths(c: dict) -> list[str]:
    """กล่อง "ความจริงที่ต้องบอกตรง ๆ" — ข้อความจากตัวเลขจริงเท่านั้น."""
    out = []
    ov = c["heat_port_overall"]
    if ov is not None:
        out.append(f"ระดับความเสี่ยงรวมของพอร์ต = <b>{ov} · {rk.LEVEL[ov]}</b> (ใช้ระดับแย่สุดของทุกมิติ ไม่ใช่ค่าเฉลี่ย)")
    for wn in c["conc"]["warnings"]:
        cls = "bad" if wn["level"] == "hard" else "flag"
        out.append(f"<span class='{cls}'>{esc(wn['ticker'])} มีน้ำหนัก {wn['weight']}% แตะหรือเกินเพดานเตือน {wn['cap']}%</span>")
    for wn in (c["sectors"]["warnings"] if c["sectors"] else []):
        cls = "bad" if wn["level"] == "hard" else "flag"
        out.append(f"<span class='{cls}'>กลุ่ม {esc(wn['sector'])} รวม {wn['weight']}% แตะหรือเกินเพดานเตือนรายอุตสาหกรรม {wn['cap']}%</span>")
    if c["fx"]:
        out.append(esc(rk.explain_fx(c["fx"]["rate"])))
    res = c["res"]
    if c["mode"] == "optimize" and not res["feasible"]:
        out.append(f"<span class='bad'>ถึงเป้าไม่ได้</span> — รายชื่อนี้ทำ E(rp) ได้สูงสุด {pct(res['e_max'])} "
                   f"ขาดจากเป้า {pct(c['target'])} อยู่ {pct(res['shortfall'])}")
    for h in c["hedges"]:
        if h["metric"]:
            out.append(f"มิติ{esc(rk.metric_label(h['metric']))}อยู่ระดับ {h['score']} · {rk.LEVEL[h['score']]}")
    out.append(f"ตัวเลขทั้งหมดคิดจากอดีต {c['win_txt']} (in-sample) และสมมติฐาน CAPM — อนาคตอาจไม่เหมือนเดิม")
    return out


def holdings_table(c: dict) -> str:
    t = c["tickers"]
    shares = c.get("holding_values")
    head = "<tr><th>หุ้น</th><th>น้ำหนัก</th><th style='width:20%'></th>"
    if shares:
        head += "<th>จำนวนหุ้น</th><th>ราคาปิดล่าสุด</th><th>มูลค่า (USD)</th>"
    head += f"<th>β</th><th>E(r) CAPM</th><th>CAGR ย้อน {esc(c['win_txt'])} (อดีต)</th><th>σ ไม่เป็นระบบ</th></tr>"
    rows = ""
    for i, (tk, wd) in enumerate(zip(t, c["w_disp"])):
        rows += f"<tr><td>{esc(tk)}</td><td>{wd}%</td><td><div class='bar' style='width:{float(wd):.2f}%'></div></td>"
        if shares:
            h = shares[tk]
            rows += f"<td>{h['shares']}</td><td>{rk.usd(h['price'])}</td><td>{rk.usd(h['value'])}</td>"
        rows += (f"<td>{num(c['beta'][i], 3)}</td><td>{pct(c['er'][i])}</td><td>{pct(c['hist'][i])}</td>"
                 f"<td>{pct(math.sqrt(c['cov_e'][i, i]))}</td></tr>")
    tot = f"<tr class='port'><td><b>รวม</b></td><td><b>{sum(c['w_disp'])}%</b></td><td></td>"
    if shares:
        tot += f"<td></td><td></td><td><b>{rk.usd(c['total_value'])}</b></td>"
    tot += "<td></td><td></td><td></td><td></td></tr>"
    cn = c["conc"]
    note = (f"<p class='explain'>ตัวใหญ่สุดคือ {esc(cn['top_ticker'])} ({cn['top_weight']}%) · "
            f"{esc(rk.explain_eff(cn['effective_n']))}</p>")
    src = ("<p class='note'>มูลค่า = จำนวนหุ้น × ราคาปิดล่าสุด (ราคาจริง ไม่ปรับปันผล) · น้ำหนักคิดจากมูลค่า</p>"
           if shares else "")
    return f"<div class='tbl'><table>{head}{rows}{tot}</table></div>{note}{src}"


def heat_table(c: dict) -> str:
    cols = [m for m in rk.HEAT_ORDER]
    head = "<tr><th>หุ้น</th>" + "".join(f"<th>{esc(rk.HEAT[m]['label'])}</th>" for m in cols) + "<th>รวม</th></tr>"
    rows = ""
    for r in c["heat_rows"]:
        rows += f"<tr><td>{esc(r['ticker'])}</td>" + "".join(hcell(r["cells"][m]) for m in cols)
        rows += f"<td>{chip(r['overall'])}</td></tr>"
    pr = c["heat_port"]
    rows += ("<tr class='port'><td><b>ทั้งพอร์ต</b></td>" + "".join(hcell(pr[m]) for m in cols)
             + f"<td>{chip(c['heat_port_overall'])}</td></tr>")
    anchor = c["corr_anchor"]
    note = (f"<p class='note'>คอลัมน์ correlation เทียบกับ{'หุ้นหลัก ' + esc(anchor) if anchor else 'ดัชนีตลาด (น้ำหนักสูงสุดเสมอกันหลายตัว)'}"
            f"{' — ช่องของ ' + esc(anchor) + ' เองแสดงเป็นเทา' if anchor else ''} · "
            "แถว \"ทั้งพอร์ต\": น้ำหนัก = ตัวใหญ่สุด · ผันผวน/β = ของพอร์ต · ร่วงสูงสุด = พอร์ตในช่วงวิกฤตที่แย่สุด · "
            "correlation = ค่าเฉลี่ยถ่วงน้ำหนักทุกคู่ · สภาพคล่อง = ตัวที่ต่ำสุดที่ถืออยู่ · "
            "ดอกเบี้ย = ความไวของพอร์ต (Σ น้ำหนัก × ความไวรายตัว) · "
            "ช่อง \"รวม\" = ระดับแย่สุดในแถว · ช่องเทา = ข้อมูลไม่พอ ไม่ได้แปลว่าปลอดภัย</p>")
    legend = "<p class='note'>" + " ".join(chip(s) for s in range(1, 6)) + " " + chip(None) + "</p>"
    return f"<div class='tbl'><table>{head}{rows}</table></div>{legend}{note}"


def threshold_table() -> str:
    head = "<tr><th>มิติ</th>" + "".join(f"<th>{chip(s)}</th>" for s in range(1, 6)) + "</tr>"
    rows = "".join(f"<tr><td>{esc(rk.HEAT[m]['label'])}</td>" + "".join(f"<td>{esc(x)}</td>" for x in rk.HEAT[m]["ranges"])
                   + "</tr>" for m in rk.HEAT_ORDER)
    return f"<div class='tbl'><table>{head}{rows}</table></div>"


def stress_html(c: dict) -> str:
    label = MODE_LABEL[c["mode"]]
    out = ""
    for sb in c["stress"].values():
        body = "".join(
            f"<tr><td>{esc(tk)}</td><td>{pct(r['total_return']) if r else missing()}</td>"
            f"<td>{pct(r['max_dd']) if r else missing()}</td></tr>"
            for tk, r in sb["rows"].items())
        pr, ir = sb["portfolio"], sb["index"]
        body += (f"<tr class='port'><td><b>{label}</b></td><td>{pct(pr['total_return']) if pr else missing()}</td>"
                 f"<td>{pct(pr['max_dd']) if pr else missing()}</td></tr>")
        body += (f"<tr><td>ดัชนี {esc(c['index_ticker'])}</td><td>{pct(ir['total_return']) if ir else missing()}</td>"
                 f"<td>{pct(ir['max_dd']) if ir else missing()}</td></tr>")
        gap = ("<p class='note'>ไม่ครบเกณฑ์ในช่วงนี้: " + esc("; ".join(f"{k}: {v}" for k, v in sb["gaps"].items()))
               + "</p>") if sb["gaps"] else ""
        out += (f"<div><h3>{esc(sb['label'])}</h3><div class='tbl'><table>"
                f"<tr><th>รายการ</th><th>ผลตอบแทนทั้งช่วง</th><th>ร่วงสูงสุด</th></tr>{body}</table></div>{gap}</div>")
    return out


def liquidity_html(c: dict) -> str:
    shares = c.get("holding_values")
    head = "<tr><th>หุ้น</th><th>มูลค่าซื้อขายเฉลี่ย/วัน (3 เดือน)</th><th>ระดับ</th>"
    head += "<th>มูลค่าที่ถือ ÷ มูลค่าซื้อขายต่อวัน</th></tr>" if shares else "</tr>"
    rows = ""
    for i, tk in enumerate(c["tickers"]):
        lq = c["liq"][i]
        cl = c["heat_rows"][i]["cells"]["liq"]
        rows += f"<tr><td>{esc(tk)}</td><td>{rk.usd_compact(lq['adv'])}</td><td>{chip(cl['score'])}</td>"
        if shares:
            share = (shares[tk]["value"] / lq["adv"] * 100) if lq["adv"] else None
            rows += f"<td>{'[ข้อมูลไม่พอ]' if share is None else num(share, 4) + '%'}</td>"
        rows += "</tr>"
    note = ("<p class='explain'>หุ้นใหญ่ในสหรัฐส่วนมากซื้อขายวันละหลายพันล้านดอลลาร์ ขนาดพอร์ตรายย่อยแทบไม่ขยับราคา · "
            "ระดับจะเริ่มเหลือง/แดงเมื่อหุ้นเล็กมาก ซึ่งตอนต้องขายด่วนอาจต้องยอมราคาที่แย่ลง</p>")
    return f"<div class='tbl'><table>{head}{rows}</table></div>{note}"


def rebalance_html(c: dict) -> str:
    rb = c["rebalance"]
    cls = {"เพิ่มน้ำหนัก": "act-up", "ลดน้ำหนัก": "act-down", "คง": "act-hold"}
    rows = "".join(
        f"<tr><td>{esc(r['ticker'])}</td><td>{r['current']}%</td><td>{r['target']}%</td>"
        f"<td>{'+' if r['diff'] > 0 else ''}{r['diff']}</td><td class='{cls[r['action']]}'>{r['action']}</td></tr>"
        for r in rb)
    cur, tgt = c["res"], c["rebal_res"]
    s, e = c["split"], c["split_rebal"]
    cmp_rows = "".join(f"<tr><td>{lab}</td><td>{a}</td><td>{b}</td></tr>" for lab, a, b in [
        ("E(rp) ตาม CAPM", pct(cur["e_p"]), pct(tgt["e_p"])),
        ("β พอร์ต", num(cur["beta_p"], 3), num(tgt["beta_p"], 3)),
        ("σ รวม (ต่อปี)", pct(math.sqrt(s["total_var"])), pct(math.sqrt(e["total_var"]))),
        ("σ ไม่เป็นระบบ (ต่อปี)", pct(math.sqrt(s["unsys_var"])), pct(math.sqrt(e["unsys_var"]))),
        ("สัดส่วนความเสี่ยงไม่เป็นระบบ", pct(s["unsys_share"], 1), pct(e["unsys_share"], 1)),
    ])
    basis = (f"เงื่อนไข E(rp) ไม่ต่ำกว่าเป้าที่ผู้ใช้กำหนด {pct(c['target'])}" if c["target_given"]
             else f"เงื่อนไข E(rp) ไม่ต่ำกว่าพอร์ตปัจจุบัน ({pct(cur['e_p'])}) — ถ้าได้สูงกว่าโดยความเสี่ยงไม่เป็นระบบต่ำลงด้วย ตัวหาน้ำหนักจะเลือกแบบนั้น")
    infeas = ("" if tgt["feasible"] else
              f"<p class='flag'>เป้านี้สูงเกินที่รายชื่อนี้ทำได้ — สัดส่วนเป้าคือพอร์ตที่ E(rp) สูงสุด {pct(tgt['e_max'])}</p>")
    return (f"<p class='note'>สัดส่วนเป้า = ตัวหาน้ำหนักใช้หุ้นชุดเดิม ที่{basis} แล้วหาน้ำหนักที่ความเสี่ยงไม่เป็นระบบต่ำสุด · "
            f"ห่างเกิน ±{rk.REBAL_BAND} จุด% → เพิ่มน้ำหนัก/ลดน้ำหนัก · ไม่เกิน → คง</p>{infeas}"
            f"<div class='tbl'><table><tr><th>หุ้น</th><th>ถืออยู่</th><th>สัดส่วนเป้า</th><th>ต่าง (จุด%)</th><th>ผล</th></tr>{rows}</table></div>"
            f"<div class='tbl' style='margin-top:12px'><table><tr><th>ตัวชี้วัด</th><th>พอร์ตปัจจุบัน</th><th>สัดส่วนเป้า</th></tr>{cmp_rows}</table></div>"
            "<p class='explain'>นี่คือผลคำนวณเชิงตัวเลข ไม่ใช่คำสั่งซื้อขาย · ตัวหาน้ำหนักไม่รู้เรื่องภาษี ค่าธรรมเนียม "
            "หรือเหตุผลที่คุณถือแต่ละตัว · สัดส่วนเป้าดีกว่าแค่ใน 3 ปีที่ผ่านมา (in-sample)</p>")


def frontier_html(c: dict) -> str:
    res = c["res"]
    fr = c["frontier"]
    fr_svg = svg_lines([("σ ไม่เป็นระบบต่ำสุด", [x for x, _ in fr], [y for _, y in fr], "var(--s1)")],
                       [(fr[0][0], pct(fr[0][0], 1)), (fr[-1][0], pct(fr[-1][0], 1))],
                       lambda y: pct(y, 1),
                       marker=(res["e_p"], math.sqrt(res["unsys_var"]), "พอร์ตที่เลือก"),
                       title="เป้าผลตอบแทนเทียบความเสี่ยงไม่เป็นระบบต่ำสุด")
    s, e = c["split"], c["split_eq"]
    cmp_rows = "".join(f"<tr><td>{lab}</td><td>{a}</td><td>{b}</td></tr>" for lab, a, b in [
        ("E(rp) ตาม CAPM", pct(res["e_p"]), pct(c["e_eq"])),
        ("β พอร์ต", num(res["beta_p"], 3), num(c["b_eq"], 3)),
        ("σ รวม (ต่อปี)", pct(math.sqrt(s["total_var"])), pct(math.sqrt(e["total_var"]))),
        ("σ ไม่เป็นระบบ (ต่อปี)", pct(math.sqrt(s["unsys_var"])), pct(math.sqrt(e["unsys_var"]))),
        ("สัดส่วนความเสี่ยงไม่เป็นระบบ", pct(s["unsys_share"], 1), pct(e["unsys_share"], 1)),
        (f"ผลตอบแทนย้อน {esc(c['win_txt'])} (ถือเฉย ๆ)", pct(c["hist_p"]["total_return"]), pct(c["hist_eq"]["total_return"])),
        ("ความผันผวนย้อนหลัง (ต่อปี)", pct(c["hist_p"]["vol"]), pct(c["hist_eq"]["vol"])),
        (f"ร่วงสูงสุดย้อน {esc(c['win_txt'])}", pct(c["hist_p"]["max_dd"]), pct(c["hist_eq"]["max_dd"])),
    ])
    n = len(c["tickers"])
    return (f"{fr_svg}<p class='note'>แกนนอน = เป้า E(rp) · แกนตั้ง = σ ไม่เป็นระบบต่ำสุดที่ทำได้ที่เป้านั้น · "
            "จุดสีทอง = พอร์ตที่เลือก · ยิ่งตั้งเป้าสูง ยิ่งต้องกระจุกในหุ้น β สูง ความเสี่ยงไม่เป็นระบบจึงเพิ่ม</p>"
            f"<h3 style='margin-top:14px'>เทียบกับพอร์ตแบ่งเท่ากัน</h3><div class='tbl'><table><tr><th>ตัวชี้วัด</th>"
            f"<th>พอร์ตที่คำนวณ</th><th>แบ่งเท่ากัน ({num(100 / n)}% ต่อตัว)</th></tr>{cmp_rows}</table></div>"
            "<p class='note'>ค่าย้อนหลังสมมติถือเฉย ๆ ตั้งแต่วันแรกของหน้าต่าง ไม่ปรับน้ำหนักระหว่างทาง · "
            "σ ไม่เป็นระบบของพอร์ตที่คำนวณคิดจากข้อมูล 3 ปีชุดเดียวกับที่ใช้หาน้ำหนัก (in-sample) "
            "จึงต่ำกว่าพอร์ตแบ่งเท่ากันโดยวิธีคำนวณ ไม่ใช่หลักฐานว่าอนาคตจะเป็นแบบนั้น · และสองพอร์ตมี E(rp) ไม่เท่ากัน</p>")


def sector_html(c: dict) -> str:
    if not c["sectors"]:
        return f"<p>{missing()} ดึงข้อมูลอุตสาหกรรมไม่ได้ในรอบนี้ — ดูธงในหัวข้อที่มาและเกณฑ์</p>"
    lv = {"hard": ("bad", f"เตือนแรง (≥{rk.SECTOR_HARD}%)"), "soft": ("flag", f"เตือน (≥{rk.SECTOR_SOFT}%)")}
    rows = ""
    for g in c["sectors"]["rows"]:
        if g["sector"] == rk.UNKNOWN_SECTOR:
            status = "<span class='note'>ไม่ใช้เพดาน</span>"
        elif g["level"]:
            cls, txt = lv[g["level"]]
            status = f"<span class='{cls}'>{txt}</span>"
        else:
            status = "<span class='act-hold'>ต่ำกว่าเพดาน</span>"
        rows += (f"<tr><td>{esc(g['sector'])}</td><td>{g['weight']}%</td>"
                 f"<td><div class='bar' style='width:{min(float(g['weight']), 100):.2f}%'></div></td>"
                 f"<td style='text-align:left;white-space:normal'>{esc(', '.join(g['tickers']))}</td><td>{status}</td></tr>")
    sm = c.get("sector_map") or {}
    per = "".join(
        f"<tr><td>{esc(tk)}</td><td style='text-align:left'>{esc(sm[tk]['sector']) if tk in sm else rk.UNKNOWN_SECTOR}</td>"
        f"<td style='text-align:left;white-space:normal'>{esc(sm[tk].get('industry') or '—') if tk in sm else '—'}</td></tr>"
        for tk in c["tickers"])
    n_groups = sum(1 for g in c["sectors"]["rows"] if g["sector"] != rk.UNKNOWN_SECTOR)
    return (f"<div class='tbl'><table><tr><th>กลุ่ม</th><th>น้ำหนักรวม</th><th style='width:20%'></th>"
            f"<th style='text-align:left'>หุ้นในกลุ่ม</th><th>เพดาน</th></tr>{rows}</table></div>"
            f"<p class='explain'>พอร์ตกระจายอยู่ใน {n_groups} กลุ่มอุตสาหกรรม · หุ้นกลุ่มเดียวกันมักโดนข่าวเดียวกัน "
            f"(กฎหมาย ต้นทุน วัฏจักร) ถือหลายตัวในกลุ่มเดียวจึงกระจายความเสี่ยงได้น้อยกว่าที่เห็นจากจำนวนหุ้น</p>"
            f"<h3 style='margin-top:14px'>รายตัว</h3><div class='tbl'><table><tr><th>หุ้น</th>"
            f"<th style='text-align:left'>กลุ่ม</th><th style='text-align:left'>อุตสาหกรรมย่อย</th></tr>{per}</table></div>"
            f"<p class='note'>ที่มา: Nasdaq screener (tier 3 · as-of {esc(c['sector_src']['as_of'])}) · การจัดกลุ่มแบบ Nasdaq ไม่ใช่ GICS · "
            f"กองทุน ETF และหุ้นที่หาไม่เจอรวมเป็น \"{rk.UNKNOWN_SECTOR}\" และไม่ได้ดูว่าข้างในถือหุ้นกลุ่มไหน · "
            f"เพดานเตือน {rk.SECTOR_SOFT}%/{rk.SECTOR_HARD}% เตือนอย่างเดียว</p>")


def fx_html(c: dict) -> str:
    fx = c["fx"]
    if not fx:
        return f"<p>{missing()} ดึงค่าเงินบาท (FRED DEXTHUS) ไม่ได้ในรอบนี้</p>"
    shares = c.get("total_value") is not None
    head = "<tr><th>สถานการณ์</th><th>1 USD = ? บาท</th><th>มูลค่าเป็นบาทเปลี่ยน</th>"
    head += "<th>มูลค่าพอร์ต (บาท)</th></tr>" if shares else "</tr>"
    rows = ""
    for sc in fx["scenarios"]:
        rows += (f"<tr><td>{esc(sc['label'])}</td><td>{sc['rate']}</td>"
                 f"<td>{'—' if sc['shock'] == 0 else rk.signed_pct(sc['shock'])}</td>")
        rows += f"<td>{rk.thb(sc['value_thb'])}</td></tr>" if shares else "</tr>"
    wrows = ""
    for w in fx["windows"]:
        if "ret_usd" not in w:
            wrows += f"<tr><td>{esc(w['label'])}</td>" + f"<td>{missing()}</td>" * 5 + "</tr>"
            continue
        wrows += (f"<tr><td>{esc(w['label'])}</td><td>{num(w['fx_start'])} → {num(w['fx_end'])}</td>"
                  f"<td>{pct(w['fx_change'])}</td><td>{pct(w['ret_usd'])}</td><td>{pct(w['ret_thb'])}</td>"
                  f"<td>{pct(w['max_dd_thb'])}</td></tr>")
    label = MODE_LABEL[c["mode"]]
    unit = "" if shares else ("<p class='note'>ใส่เป็นสัดส่วน % จึงแสดงเป็น % เท่านั้น — "
                              "ถ้าต้องการมูลค่าเป็นบาท ให้ใส่เป็นจำนวนหุ้น</p>")
    return (f"<p class='explain'>{esc(rk.explain_fx(fx['rate']))}</p>"
            f"<h3 style='margin-top:14px'>สมมติค่าเงินเปลี่ยน (ราคาหุ้นเท่าเดิม)</h3>"
            f"<div class='tbl'><table>{head}{rows}</table></div>{unit}"
            f"<h3 style='margin-top:14px'>{esc(label)} คิดเป็นบาท ด้วยค่าเงินจริงของแต่ละช่วง</h3>"
            f"<div class='tbl'><table><tr><th>ช่วง</th><th>USD/THB ต้น → ปลาย</th><th>ค่าเงินเปลี่ยน</th>"
            f"<th>ผลตอบแทน (USD)</th><th>ผลตอบแทน (บาท)</th><th>ร่วงสูงสุด (บาท)</th></tr>{wrows}</table></div>"
            f"<p class='note'>ที่มา: FRED DEXTHUS (tier 1) ค่าล่าสุด {esc(fx['date'])} · วันที่ไม่มีค่าเงิน (วันหยุดคนละชุดกับตลาดหุ้น) "
            f"ใช้ค่าล่าสุดที่มีไม่เกิน {rk.FFILL_MAX_DAYS} วัน · ค่าเงินเปลี่ยนบวก = บาทอ่อน ผลตอบแทนเป็นบาทจึงสูงกว่าเป็นดอลลาร์</p>")


def rate_html(c: dict) -> str:
    rs = c["rate_sens"]
    if rs["portfolio"] is None:
        return (f"<p>{missing()} คิดความไวต่อดอกเบี้ยไม่ได้ — ข้อมูล DGS10 ไม่พอ "
                f"(มี {rs['weeks']} สัปดาห์ ต้อง ≥ {rk.RATE_MIN_WEEKS})</p>")
    rows = ""
    for i, tk in enumerate(c["tickers"]):
        cl = c["heat_rows"][i]["cells"]["rate"]
        st = rs["stocks"][i]
        rows += (f"<tr><td>{esc(tk)}</td><td>{rk.signed_pct(c['rate_disp'][i])}</td>"
                 f"<td>{num(st['r2']) if st else missing()}</td><td>{chip(cl['score'])}</td></tr>")
    pc = c["heat_port"]["rate"]
    rows += (f"<tr class='port'><td><b>{esc(MODE_LABEL[c['mode']])}</b></td><td><b>{rk.signed_pct(c['rate_port'])}</b></td>"
             f"<td>{num(rs['portfolio']['r2'])}</td><td>{chip(pc['score'])}</td></tr>")
    return (f"<div class='tbl'><table><tr><th>หุ้น</th><th>ดอกเบี้ย 10 ปี +1% หุ้นขยับ</th><th>r²</th><th>ระดับ</th></tr>"
            f"{rows}</table></div>"
            f"<p class='explain'>{esc(rk.explain_rate(c['rate_port'], rs['portfolio']['r2']))}</p>"
            f"<p class='note'>วิธีคิด: ผลตอบแทนรายสัปดาห์ของหุ้น เทียบการเปลี่ยนของ DGS10 (จุด%) {rs['weeks']} สัปดาห์ "
            f"({esc(rs['start'])} → {esc(rs['end'])} · DGS10 {rs['y_start']}% → {rs['y_end']}%) · "
            f"เป็นความสัมพันธ์ในอดีตแบบตัวแปรเดียว จึงรวมผลที่ตลาดทั้งก้อนขยับตามดอกเบี้ยด้วย · "
            f"r² ต่ำ = ดอกเบี้ยอธิบายการขยับได้น้อย ตัวเลขความไวจึงเชื่อถือได้น้อย · ที่มา: FRED DGS10 (tier 1)</p>")


# ================================================================ หน้าเต็ม
def build_html(c: dict) -> str:
    t = c["tickers"]
    res = c["res"]
    mode = c["mode"]
    label = MODE_LABEL[mode]
    s = c["split"]
    ov = c["heat_port_overall"]
    dd_p = c["port_dd"]
    beta_s = num(res["beta_p"], 3)
    vol_s = pct(math.sqrt(s["total_var"]))
    corr_s = num(c["avg_corr"]) if c["avg_corr"] is not None else "[ข้อมูลไม่พอ]"

    kpis = [
        kpi("ระดับความเสี่ยงรวม", chip(ov), "ระดับแย่สุดของทุกมิติ"),
        kpi("E(rp) ตาม CAPM", pct(res["e_p"]), rk.explain_er(pct(res["e_p"]))),
        kpi("β พอร์ต", beta_s, rk.explain_beta(beta_s)),
        kpi("ความผันผวนต่อปี", vol_s, rk.explain_vol(vol_s)),
        kpi("ร่วงสูงสุดช่วงวิกฤต", f"{dd_p['value']}%" if dd_p["value"] is not None else "[ข้อมูลไม่พอ]",
            rk.explain_dd(dd_p["value"], dd_p["label"])),
        kpi("ความเสี่ยงไม่เป็นระบบ", pct(s["unsys_share"], 1), rk.explain_unsys(pct(s["unsys_share"], 1))),
    ]
    if c.get("total_value") is not None:
        kpis.append(kpi("มูลค่าพอร์ต (USD)", rk.usd(c["total_value"]), "จำนวนหุ้น × ราคาปิดล่าสุด"))
        if c["fx"]:
            kpis.append(kpi("มูลค่าพอร์ต (บาท)", rk.thb(c["fx"]["scenarios"][2]["value_thb"]),
                            f"คิดที่ 1 USD = {c['fx']['rate']} บาท ({c['fx']['date']})"))

    truth = "<div class='truth'><h2>ความจริงที่ต้องบอกตรง ๆ</h2><ul>" + "".join(f"<li>{x}</li>" for x in truths(c)) + "</ul></div>"

    corr_body = (f"<div class='grid2'><div><p class='note'>จากผลตอบแทนราคาจริง (รวมส่วนที่ขยับตามตลาด)</p>"
                 f"{svg_matrix(t, c['corr'], 'correlation ราคาจริง')}</div>"
                 f"<div><p class='note'>จาก residual (หลังหักการขยับตามตลาด) — ส่วนที่กระจายหุ้นแล้วลดได้</p>"
                 f"{svg_matrix(t, c['corr_e'], 'correlation residual')}</div></div>"
                 f"<p class='explain'>{esc(rk.explain_corr(corr_s))}</p>")

    n = len(c["dates"])
    xi = list(range(n))
    dd_svg = svg_lines([(label, xi, list(c["dd_p"]), "var(--s1)"),
                        ("แบ่งเท่ากัน", xi, list(c["dd_eq"]), "var(--s2)"),
                        (f"ดัชนี {c['index_ticker']}", xi, list(c["dd_idx"]), "var(--s3)")],
                       [(0, c["dates"][0]), (n // 2, c["dates"][n // 2]), (n - 1, c["dates"][-1])],
                       lambda y: pct(y, 0), title=f"drawdown ย้อน {c['win_txt']}")
    stress_body = (f"{dd_svg}<div class='grid2' style='margin-top:14px'>{stress_html(c)}</div>"
                   "<p class='note'>stress ใช้น้ำหนักชุดเดียวกันถือเฉย ๆ ตลอดช่วง · หุ้นที่ไม่มีข้อมูลช่วงนั้นติด [ข้อมูลไม่พอ] "
                   "และถ้าหุ้นที่มีน้ำหนักขาดข้อมูล ตัวเลขพอร์ตของช่วงนั้นจะไม่คำนวณ</p>")

    sec08 = (sec("08", "ปรับพอร์ต — เทียบสัดส่วนที่ถือกับสัดส่วนเป้า", rebalance_html(c)) if mode == "evaluate"
             else sec("08", "เป้าผลตอบแทนเทียบความเสี่ยงไม่เป็นระบบต่ำสุด", frontier_html(c)))
    hedges = "<ol>" + "".join(f"<li>{esc(h['text'])}</li>" for h in c["hedges"]) + "</ol>"
    hedge_note = ("<p class='note'>สคริปต์เลือกมิติระดับพอร์ตที่แย่สุดไม่เกิน 3 มิติ (ระดับ 3 ขึ้นไป) แล้วเติมประโยคจากแม่แบบ · "
                  "เป็นแนวทางให้คิดต่อ ไม่ใช่คำสั่งซื้อขาย</p>")

    src = c["sources"]
    flags = "".join(f"<li class='flag'>{esc(f)}</li>" for f in c["flags"])
    title = "ตรวจความเสี่ยงพอร์ตที่ถืออยู่" if mode == "evaluate" else "จัดน้ำหนักลดความเสี่ยงไม่เป็นระบบ"
    target_txt = (f" · เป้า E(rp) {pct(c['target'])}" if c["target_given"] else "")
    gloss = "".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in GLOSSARY)

    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark">
<title>Portfolio Risk</title><style>{CSS}</style></head>
<body><main>
<h1>{title}</h1>
<p class="sub">รัน {esc(c['as_of'])} · หน้าต่างประมาณค่า {esc(c['dates'][0])} → {esc(c['dates'][-1])} ({len(c['dates']) - 1} วันทำการ){target_txt} · {len(t)} หุ้น</p>
<div class="kpis">{''.join(kpis)}</div>
{truth}
{sec("00", "สัดส่วนที่ถือ", holdings_table(c))}
{sec("01", "Heat map ความเสี่ยงรายตัว", heat_table(c))}
{sec("02", "Correlation", corr_body)}
{sec("03", "อุตสาหกรรมและการกระจุกตัว", sector_html(c))}
{sec("04", "ค่าเงินบาท", fx_html(c))}
{sec("05", "ดอกเบี้ย", rate_html(c))}
{sec("06", "Stress test และ drawdown", stress_body)}
{sec("07", "สภาพคล่อง — ขายออกง่ายแค่ไหน", liquidity_html(c))}
{sec08}
{sec("09", "แนวทางลดความเสี่ยง", hedges + hedge_note)}
<section><h2>ที่มาและเกณฑ์</h2><ul>
<li>ราคา: yfinance adj_close (tier 3 · as-of {esc(src['price_as_of'])}) · ดัชนีสำหรับ β = {esc(c['index_ticker'])}</li>
<li>มูลค่าซื้อขายต่อวัน: ราคาปิดจริง × volume เฉลี่ย 3 เดือนล่าสุด (yfinance tier 3)</li>
<li>r_RF: FRED {esc(src['rf'])} วันที่ {esc(src['rf_date'])} (tier 1) = {pct(c['rf'])}</li>
<li>r_M: {esc(src['rm_detail'])}</li>
<li>ข้อจำกัด: r_RF เป็นค่าวันนี้ แต่ r_M เป็นค่าเฉลี่ยย้อนหลัง — คนละช่วงเวลา ส่วนต่าง r_M − r_RF ({pct(c['rm'] - c['rf'])}) จึงอาจต่ำกว่าส่วนต่างจริงของช่วงเดียวกัน</li>
<li>β และ covariance: {("daily return " + str(len(c['dates']) - 1) + " วัน") if not c['short_history'] else "daily return คิดทีละคู่จากวันที่ทั้งคู่มีข้อมูล (หุ้นประวัติไม่ครบ 3 ปี: " + esc(", ".join(c['short_history'])) + ")"} · annualize ด้วย 252 วัน · Σ_ε เต็มเมทริกซ์</li>
<li>สูตร: 8.8 E(rp)=Σwᵢ E(rᵢ) · 8.9 σ²p=w'Σw · (12) CAPM · ตัวหาน้ำหนัก = min w'Σ_ε w ภายใต้ Σw=1, w≥0 (ห้ามขายชอร์ต), β'w ≥ β เป้า</li>
<li>เพดานเตือนหุ้นตัวเดียว {rk.SOFT_CAP}% / {rk.HARD_CAP}% · รายอุตสาหกรรม {rk.SECTOR_SOFT}% / {rk.SECTOR_HARD}% — เตือนอย่างเดียว ตัวหาน้ำหนักไม่ได้ใช้เป็นข้อจำกัด · ในการจัดอันดับแนวทางลดความเสี่ยง อุตสาหกรรมเกินเพดานเตือนนับเป็นระดับ {rk.SECTOR_SCORE['soft']} และเกินเพดานเตือนแรงนับเป็นระดับ {rk.SECTOR_SCORE['hard']}</li>
<li>อุตสาหกรรม: Nasdaq screener (tier 3) · ค่าเงิน: FRED DEXTHUS (tier 1) · ดอกเบี้ย: FRED DGS10 (tier 1)</li>
{flags}</ul>
<h3 style="margin-top:12px">เกณฑ์สี heat map</h3>{threshold_table()}</section>
<section><h2>อภิธานศัพท์</h2><dl class="gloss">{gloss}</dl></section>
<p class="note"><b>ข้อจำกัดความรับผิดชอบ:</b> เอกสารนี้เป็นการคำนวณเชิงตัวเลขจากข้อมูลในอดีตและสมมติฐาน CAPM
เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน β และ covariance ในอดีตอาจไม่คงที่ในอนาคต</p>
</main></body></html>"""
