"""profiles/tommun.py — สเปกเมโมของ 'ทอมมุน' (นักวิเคราะห์งบการเงิน)

ต่างจากโทนี่ 5 จุด:
  1. section 11 อัน (§0–§10) ภาคผนวกอยู่ที่ §10 ไม่ใช่ §9
  2. YAML ไม่มี price · เพิ่ม currency + accounting_standard (US GAAP / IFRS ของ FPI)
  3. ฟิลด์ต้องห้ามเพิ่มสายราคา/มูลค่า — ทอมมุนไม่ตัดสินราคาเด็ดขาด
  4. §0–§8 บังคับบรรทัดปิดท้าย 'สองบรรทัด' — (อนุมาน: ...) และ (ความเห็น: ...)
     (§9 PLAIN-LANGUAGE SUMMARY ไม่นับ — ห้ามมีข้อเท็จจริงใหม่ จึงบังคับ 'อนุมาน' ไม่ได้)
  5. ภาคผนวกมี 3 ตาราง — เพิ่มตารางสมมติฐาน 3 ช่อง และทุก [สมมติฐาน: ...] ในเนื้อเมโม
     ต้องมีแถวรองรับ

Option B — CAPM-only, annual tax selection, book weights and debt bounds.
Structured audit tables live in §5; Decimal recomputes NOPAT/IC/ROIC/WACC/spread/flag.
Synthetic fixtures prove arithmetic, not truth of the cited filing inputs.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import re
from datetime import date

from ..core import POST_FILING_LINE, Profile, TableSpec, table_rows

ANNUAL_HEADERS = 'FY pretax tax_provision ETR statutory T_used EBIT D_begin P_begin E_begin leases_begin D_end P_end E_end leases_end IC_avg NOPAT ROIC source tax_source'.split()
WACC_FIELDS = 'FY D P E D_avg interest_expense T_used Rf industry_beta ERP k_e k_p w_d w_p w_e k_d kd_lower kd_upper WACC_low WACC_high spread_low spread_high flag_low flag_high book_wacc spread flag choice debt_coverage_amount'.split()
CASH_HEADERS = 'FY cash IC_avg NOPAT cash_IC_pct direction explanation source'.split()
CASH_EXPLANATIONS = {'lower_positive':'กด ROIC บวกให้ต่ำลง','less_negative':'ทำให้ ROIC ติดลบน้อยลง','unchanged':'ROIC ไม่เปลี่ยน','N/A':'ไม่สรุปทิศทาง'}
NA = '[ข้อมูลไม่พอ]'
OFFICIAL = re.compile(r'\[(?:10-K|20-F|40-F)[^\]]*Item[^\]]*\]', re.I)
NUMBER = re.compile(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?%?')


def semantic_number(value, label, fail):
    """Whole-cell finite Decimal only. NA is explicit, never a guessed zero."""
    s = str(value).strip()
    if s == NA:
        return None
    if len(s) > 100 or not NUMBER.fullmatch(s):
        fail('13-tommun-number', f'{label}: ต้องเป็น finite Decimal หรือ {NA}; พบ {s!r}')
        return None
    try:
        n = Decimal(s.rstrip('%').replace(',', ''))
        if n.is_finite():
            return n
    except InvalidOperation:
        pass
    fail('13-tommun-number', f'{label}: nonfinite Decimal')
    return None


def audit_table(chunk, name, headers, fail, required=True):
    matches = list(re.finditer(r'^### ' + re.escape(name) + r'\s*$', chunk, re.M))
    if len(matches) != 1:
        if required or matches:
            fail('12-tommun-schema', f'§5 ต้องมี {name} หนึ่งตาราง')
        return []
    tail = chunk[matches[0].end():]
    tail = re.split(r'^### ', tail, maxsplit=1, flags=re.M)[0]
    rows = table_rows(tail.splitlines())
    if not rows or rows[0][1] != headers or not rows[0][2]:
        fail('12-tommun-schema', f'{name}: headers ต้องเป็น ' + ' | '.join(headers))
        return []
    out = []
    for _, cells, head in rows[1:]:
        if head or len(cells) != len(headers) or any(not c for c in cells):
            fail('12-tommun-schema', f'{name}: malformed/empty row')
        else:
            out.append(dict(zip(headers, cells)))
    if not out:
        fail('12-tommun-schema', f'{name}: ไม่มี data rows')
    return out


def spread_flag(spread):
    return 'สร้างมูลค่าชัด' if spread > 5 else 'ก้ำกึ่ง' if spread >= 0 else 'ทำลายมูลค่า'


# กฎ 20 — ห้ามพูดแนวโน้ม ROIC ข้ามปีที่เงินสดใน IC ต่างกันเกิน 15 จุด นอก §5
# (เพิ่ม 2026-10-09 จากเมโม BWXT: §5 เตือนถูกว่าห้ามเทียบ FY2021 กับ FY2025
#  แต่ exec_summary เขียน "ต่ำสุดในห้าปี" และ §9 เขียน "ผลตอบแทนลดลงเรื่อย ๆ" แล้ว PASS)
# ยอมรับเฉพาะ ROIC ที่หักเงินสด — ROIC ตัด goodwill ยังมีเงินสดในตัวหาร
# (BWXT: เงินสด 2.45% → 21.44% ของ IC ตัด goodwill ห่างยิ่งกว่าแบบรวม)
CASH_GAP_LIMIT = Decimal(15)
ROIC_ANCHOR = r'ROIC|return on (?:invested )?capital|ผลตอบแทน(?!\s*(?:ต่อ|ให้|แก่|คืน)?\s*(?:ส่วนของ)?ผู้ถือหุ้น|\s*ต่อสินทรัพย์)'
OTHER_METRIC = r'\bRO[EA]\b|\bOCF\b|\bFCF\b|มาร์จิ้น|\bmargin|รายได้|ยอดขาย|\baccrual|\bcapex\b|สินค้าคงเหลือ|ลูกหนี้|กำไรสุทธิ|book WACC|ต้นทุนเงินทุน'
METRIC = re.compile(r'(?P<roic>' + ROIC_ANCHOR + r')|(?P<other>' + OTHER_METRIC + r')', re.I)
TREND = re.compile(
    r'(?P<window>(?:ต่ำ|สูง)(?:ที่)?สุด\s*(?:ใน|ในรอบ)\s*(?:\d+|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ)\s*ปี'
    r'|(?:ลด|เพิ่ม|ขยับ|ไต่|ร่วง|ปรับ|ดี|แย่)(?:ลง|ขึ้น)?\s*(?:อย่าง)?(?:ต่อเนื่อง|เรื่อย\s*ๆ|ทุกปี|ติดต่อกัน|เป็นขั้นบันได)'
    r'|(?:แนวโน้ม|ทิศทาง)\s*(?:ลดลง|ขาลง|ขาขึ้น|เพิ่มขึ้น)'
    r'|(?:lowest|highest)\s+in\s+\w+\s+years|\d+-year\s+(?:low|high)'
    r'|(?:declin|ris|fall|fell|improv|deteriorat)\w*\s+(?:steadily|every year|each year|consecutively))'
    r'|(?P<yoy>(?:ลด|เพิ่ม|ขยับ|ร่วง|ปรับ)(?:ลง|ขึ้น)?\s*(?:จาก|เหลือ|มาอยู่ที่)'
    r'|(?:fell|rose|declined|increased|dropped)\s+(?:from|to))', re.I)
CASH_QUALIFIER = re.compile(r'หักเงินสด|ไม่รวมเงินสด|ตัดเงินสด|ไม่นับเงินสด|excl(?:uding|\.)?\s+cash|ex-cash|cash-excluded|net of cash', re.I)
READING_NEGATION = re.compile(r'(?:ไม่ได้แปลว่า|ห้าม(?:อ่าน|สรุป)ว่า|ไม่ควร(?:อ่าน|สรุป)ว่า|ไม่อาจสรุปว่า|อย่า(?:อ่าน|สรุป)ว่า)[^\n]{0,30}$')
NEAR = 60


def roic_trend_check(cash, meta, lines, heads, fail):
    """Cross-year ROIC claims outside §5 need cash-excluded ROIC when the cash gap > 15 pts."""
    pct = {}
    for row in cash:
        try:
            v = Decimal(row['cash_IC_pct'].rstrip('%').replace(',', ''))
        except (InvalidOperation, AttributeError):
            continue
        if v.is_finite() and re.fullmatch(r'FY\d{4}', row['FY']):
            pct[row['FY']] = v
    if len(pct) < 2:
        return
    years = sorted(pct)
    latest = years[-1]
    summary = meta.get('exec_summary')
    units = [('exec_summary', str(s)) for s in summary] if isinstance(summary, list) else []
    for pos, (num, start) in enumerate(heads):
        if num in (8, 9):
            end = heads[pos+1][1] if pos+1 < len(heads) else len(lines)
            units += [('§' + str(num), ln) for ln in lines[start+1:end]]
    for where, unit in units:
        for t in TREND.finditer(unit):
            before = unit[max(0, t.start()-NEAR):t.start()]
            metrics = list(METRIC.finditer(before))
            if not metrics or not metrics[-1].group('roic'):
                continue  # วลีแนวโน้มเป็นของตัวชี้วัดอื่น
            if READING_NEGATION.search(unit[:t.start()]):
                continue  # ประโยคเตือนว่า "ไม่ได้แปลว่า ... ลดลงต่อเนื่อง"
            if CASH_QUALIFIER.search(before[metrics[-1].start():]):
                continue
            named = sorted(y for y in set(re.findall(r'FY\d{4}', unit)) if y in pct and y != latest)
            base = (named[0] if named else years[-2]) if t.group('yoy') else years[0]
            gap = abs(pct[latest] - pct[base])
            if gap > CASH_GAP_LIMIT:
                fail('20-tommun-roic-trend',
                     f'{where}: "{t.group().strip()}" เทียบ ROIC {base}→{latest} ที่เงินสดใน IC ต่างกัน '
                     f'{gap.quantize(Decimal("0.01"), ROUND_HALF_UP)} จุด (>15) — ใช้ ROIC หักเงินสดและเขียนกำกับว่าใช้ตัวไหน: '
                     + unit.strip()[:120])


def check_semantics(text, meta, lines, heads, fail):
    # Reject actual data/formula usage, not routing prose or a negated warning.
    for ln in lines:
        for clause in re.split(r';|แต่|\bbut\b', ln, flags=re.I):
            active = re.split(r'(?:ไม่ได้ใช้|ไม่ใช้|ไม่ใช่|ห้ามใช้|ห้าม|do not use|not using)', clause, maxsplit=1, flags=re.I)[0]
            bad = re.search(r'\bget_price_history\b|\bP_?0\b\s*(?:[=:|]|\d)|(?:stock\s*price|ราคาหุ้น|\bGDP\b)[^\n]*?(?:[=:|]|\d)|(?:(?<![A-Za-z0-9_])k_?e(?![A-Za-z0-9_])|cost of equity)[^\n]*(?:Gordon|debt[ -]?plus|หนี้บวกส่วนเพิ่ม|เฉลี่ย|averag)|(?:Gordon|debt[ -]?plus|หนี้บวกส่วนเพิ่ม)[^\n]*(?:[=\d]|ใช้คำนวณ|method|model)', active, re.I)
            if bad:
                fail('14-tommun-method', 'ห้ามใช้ราคา/P0/GDP/get_price_history หรือ k_e นอก CAPM: ' + ln.strip())
            proxy = re.search(r'(?:(?<![A-Za-z0-9_])k_?d(?![A-Za-z0-9_])|cost of debt)[^\n]*(?:cash interest|coupon proxy|เงินสดจ่ายดอกเบี้ย)', active, re.I)
            warning = re.search(r'ไม่ใช้แทน|not used as (?:a )?proxy',clause,re.I)
            assignment = re.search(r'(?<![A-Za-z0-9_])k_?d\s*[=:|]\s*(?:cash interest|coupon|เงินสดจ่ายดอกเบี้ย)',active,re.I)
            if proxy and (not warning or assignment):
                fail('17-tommun-kd', 'ห้าม cash-interest/debt หรือ coupon proxy: ' + ln.strip())
    pos = next((i for i, (n, _) in enumerate(heads) if n == 5), None)
    chunk = '' if pos is None else '\n'.join(lines[heads[pos][1]:heads[pos+1][1] if pos+1 < len(heads) else len(lines)])
    annual = audit_table(chunk, 'AUDIT ANNUAL', ANNUAL_HEADERS, fail)
    wr = audit_table(chunk, 'AUDIT WACC', 'field value source unit as_of coverage'.split(), fail)
    cash = audit_table(chunk, 'AUDIT CASH', CASH_HEADERS, fail)
    debt = audit_table(chunk, 'AUDIT DEBT', 'instrument balance effective_rate source'.split(), fail, required=False)
    if cash:
        roic_trend_check(cash, meta, lines, heads, fail)
    if not annual or not wr or not cash:
        return
    w = {}
    for row in wr:
        k = row['field']
        if k in w or k not in WACC_FIELDS:
            fail('12-tommun-schema', f'AUDIT WACC duplicate/unknown field {k}')
        w[k] = row['value']
        if row['value'] == NA:
            if row['unit'] in ('N/A',NA) or not row['coverage']:
                fail('12-tommun-source',k+': NA ต้องประกาศ unit และ blocker/coverage')
            continue  # gated/unavailable inputs must not invent sources or dates
        try:
            date.fromisoformat(row['as_of'])
        except ValueError:
            fail('12-tommun-source', f'{k}: as_of ต้องเป็น ISO date')
        cite = OFFICIAL.search(row['source']) or re.search(r'\[tier[23]\]|\[FRED[^\]]*DGS10[^\]]*tier1[^\]]*\]', row['source'], re.I)
        if not cite or row['unit'] in ('N/A', NA) or not row['coverage']:
            fail('12-tommun-source', f'{k}: source/unit/as_of/coverage ต้องระบุ')
        if k in ('D','P','E','D_avg','interest_expense','kd_upper','k_p') and row['value'] != NA and not OFFICIAL.search(row['source']):
            fail('12-tommun-source', f'{k}: ต้องมี official filing source')
        if k == 'Rf' and not re.search(r'\[FRED[^\]]*DGS10[^\]]*tier1[^\]]*\]',row['source'],re.I):
            fail('12-tommun-source','Rf ต้อง FRED DGS10 tier1 source')
        if k in ('industry_beta','ERP') and (not re.search(r'\[tier3\]',row['source'],re.I) or 'damodaran' not in row['source'].lower()):
            fail('12-tommun-source',k+' ต้อง Damodaran tier3 source')
        if k == 'industry_beta' and (not re.fullmatch(r'Industry group:\s*\S.*',row['coverage'],re.I) or re.search(r'company|stock\s*beta|N/A|ข้อมูลไม่พอ',row['coverage'],re.I)):
            fail('14-tommun-capm','industry_beta coverage ต้อง Industry group: <industry name> ไม่ใช่ company beta')
    if set(w) != set(WACC_FIELDS):
        fail('12-tommun-schema', 'AUDIT WACC ต้องมี fields: ' + ' | '.join(WACC_FIELDS))
        return
    if not re.fullmatch(r'FY\d{4}', w['FY']):
        fail('12-tommun-schema', 'FY ต้องเป็น FYyyyy')
        return
    if len({r['FY'] for r in annual}) != len(annual) or len({r['FY'] for r in cash}) != len(cash):
        fail('12-tommun-schema', 'duplicate annual/cash FY')
    if {r['FY'] for r in annual} != {r['FY'] for r in cash}:
        fail('12-tommun-schema', 'cash FY ต้องตรง annual FY ทุกปี')
    if w['FY'] != max(r['FY'] for r in annual):
        fail('12-tommun-schema', 'WACC ต้องใช้ปีล่าสุดของ annual audit')

    def expect(raw, want, rule, label):
        got = semantic_number(raw, label, fail)
        if want is None:
            if str(raw).strip() != NA:
                fail(rule, f'{label}: คำนวณไม่ได้ ต้องเป็น {NA}')
        elif got is None:
            fail(rule, f'{label}: ต้องได้ {want} ไม่ใช่ N/A')
        else:
            digits = len(str(raw).rstrip('%').split('.')[1]) if '.' in str(raw) else 0
            tol = Decimal(1).scaleb(-digits)/2 + Decimal('0.000000000001')
            if abs(got-want) > tol:
                fail(rule, f'{label}: คิดซ้ำได้ {want} แต่พบ {raw}')

    parsed = {}
    for a in annual:
        fy = a['FY']
        if not re.fullmatch(r'FY\d{4}', fy):
            fail('12-tommun-schema', 'annual FY ต้องเป็น FYyyyy')
        if not OFFICIAL.search(a['source']):
            fail('12-tommun-source', fy + ': annual source ต้องเป็น official filing')
        nums = {k: semantic_number(a[k], fy+' '+k, fail) for k in ANNUAL_HEADERS if k not in ('FY','source','tax_source')}
        parsed[fy] = nums
        p, provision = nums['pretax'], nums['tax_provision']
        etr = provision/p*100 if p is not None and p != 0 and provision is not None else None
        expect(a['ETR'], etr, '15-tommun-tax', fy+' ETR')
        effective = p is not None and p > 0 and etr is not None and 0 <= etr <= 50
        fallback = p is not None and (p <= 0 or (etr is not None and not 0 <= etr <= 50))
        used = etr if effective else nums['statutory'] if fallback else None
        statutory = nums['statutory']
        if statutory is not None:
            if not 0 <= statutory <= 100 or not OFFICIAL.search(a['tax_source']) or not re.search(r'tax\s*note|ภาษี|income taxes', a['tax_source'], re.I) or not re.search(r'\b'+fy+r'\b',a['tax_source']):
                fail('15-tommun-tax', fy+': statutory ต้องมี official tax-note citation; ห้าม auto21')
        expect(a['T_used'], used, '15-tommun-tax', fy+' T_used')
        for k in ('D_begin','D_end','P_begin','P_end','leases_begin','leases_end'):
            balance = nums[k]
            if balance is not None and balance < 0:
                fail('16-tommun-book', fy+' '+k+': ต้องเป็น nonnegative book balance')
        components = [nums[k+'_'+end] for end in ('begin','end') for k in ('D','P','E','leases')]
        ic = sum(components)/2 if all(v is not None for v in components) else None
        expect(a['IC_avg'], ic, '16-tommun-book', fy+' IC_avg (includes operating leases; no cash subtraction)')
        nopat = nums['EBIT']*(1-used/100) if nums['EBIT'] is not None and used is not None else None
        expect(a['NOPAT'], nopat, '15-tommun-tax', fy+' NOPAT')
        roic = nopat/ic*100 if nopat is not None and ic is not None and ic > 0 else None
        expect(a['ROIC'], roic, '16-tommun-book', fy+' ROIC goodwill-inclusive')
        nums.update(derived_ic=ic, derived_nopat=nopat, derived_roic=roic, derived_tax=used)
    latest = parsed.get(w['FY'])
    if latest is None:
        fail('12-tommun-schema', 'WACC FY missing annual row')
        return
    numeric_fields = [k for k in WACC_FIELDS if k not in ('FY','flag','choice','flag_low','flag_high')]
    wn = {k: semantic_number(w[k], k, fail) for k in numeric_fields}
    for k in ('D','P','E'):
        expect(w[k], latest[k+'_end'], '16-tommun-book', k+' end-year excluding leases')
    davg = (latest['D_begin']+latest['D_end'])/2 if latest['D_begin'] is not None and latest['D_end'] is not None else None
    expect(w['D_avg'], davg, '16-tommun-book', 'D_avg')
    expect(w['T_used'], latest['derived_tax'], '15-tommun-tax', 'debt shield T_used same latest year')
    capm = wn['Rf']+wn['industry_beta']*wn['ERP'] if all(wn[k] is not None for k in ('Rf','industry_beta','ERP')) else None
    expect(w['k_e'], capm, '14-tommun-capm', 'k_e = Rf + industry_beta * ERP only')
    d,p,e = wn['D'],wn['P'],wn['E']
    valid = d is not None and p is not None and e is not None and d >= 0 and p >= 0 and e > 0
    total = d+p+e if valid else None
    for k, balance in (('w_d',d),('w_p',p),('w_e',e)):
        expect(w[k], balance/total*100 if valid else None, '16-tommun-book', k)
    if wn['k_p'] is not None and wn['k_p'] < 0:
        fail('16-tommun-book', 'k_p ห้ามติดลบ; unavailable → dependent WACC/spread NA')
    kd = None
    bounded = False
    supported_upper = None
    if d == 0:
        kd = Decimal(0)
        expect(w['k_d'], kd, '17-tommun-kd', 'debt-free k_d')
    elif d is not None and d > 0:
        if wn['interest_expense'] is not None:
            kd = wn['interest_expense']/davg*100 if davg is not None and davg > 0 and wn['interest_expense'] >= 0 else None
            expect(w['k_d'], kd, '17-tommun-kd', 'k_d accrual interest_expense / D_avg')
        else:
            expect(w['k_d'], None, '17-tommun-kd', 'missing-interest k_d point estimate prohibited')
            if wn['kd_upper'] is not None:
                bounded = True
                expect(w['kd_lower'], Decimal(0), '17-tommun-kd', 'kd_lower')
                amounts, rates = [], []
                for row in debt:
                    amount = semantic_number(row['balance'],'debt balance',fail)
                    rate = semantic_number(row['effective_rate'],'debt effective rate',fail)
                    if amount is None or rate is None or amount <= 0 or rate < 0 or not OFFICIAL.search(row['source']):
                        fail('17-tommun-kd', 'AUDIT DEBT ต้องมี balance/effective_rate/official source ทุก tranche; coupon proxy ไม่ได้')
                    else:
                        amounts.append(amount); rates.append(rate)
                upperrow = next(r for r in wr if r['field']=='kd_upper')
                if not amounts or sum(amounts) != d or not re.search(r'all interest-bearing debt excluding leases',upperrow['coverage'],re.I):
                    fail('17-tommun-kd', 'upper bound ต้อง prove coverage ALL debt excluding leases')
                expect(w['debt_coverage_amount'], d, '17-tommun-kd', 'debt coverage amount')
                if rates:
                    supported_upper = max(rates)
                    expect(w['kd_upper'], supported_upper, '17-tommun-kd', 'maximum effective rate ALL debt')
                if wn['kd_upper'] < 0:
                    fail('17-tommun-kd', 'negative kd_upper')

    def wa(rate):
        tax = latest['derived_tax']
        kp = wn['k_p'] if p else Decimal(0)
        if not valid or tax is None or capm is None or kp is None or rate is None:
            return None
        return (d*rate*(1-tax/100)+p*kp+e*capm)/total

    roic = latest['derived_roic']
    chosen = wa(kd)
    derived_flag = spread_flag(roic-chosen) if roic is not None and chosen is not None else 'N/A'
    if bounded:
        lo,hi = wa(Decimal(0)),wa(supported_upper)
        sl,sh = (roic-hi,roic-lo) if roic is not None and lo is not None and hi is not None else (None,None)
        for k,v in (('WACC_low',lo),('WACC_high',hi),('spread_low',sl),('spread_high',sh)):
            expect(w[k],v,'17-tommun-kd',k)
        for k,v in (('flag_low',sh),('flag_high',sl)):
            if w[k] != (spread_flag(v) if v is not None else 'N/A'):
                fail('17-tommun-kd',k+' ต้อง derive ที่ WACC endpoint ของตนเอง')
        stable = sl is not None and sh is not None and spread_flag(sl)==spread_flag(sh)
        chosen = hi if stable else None
        derived_flag = spread_flag(sl) if stable else 'N/A'
        choice = 'high' if stable else 'N/A'
    else:
        choice = 'exact' if chosen is not None else 'N/A'
        for k in ('WACC_low','WACC_high','spread_low','spread_high','kd_lower','kd_upper'):
            expect(w[k],None,'17-tommun-kd',k)
        if w['flag_low'] != 'N/A' or w['flag_high'] != 'N/A':
            fail('17-tommun-kd','no bounds → endpoint flags N/A')
    if w['choice'] != choice:
        fail('17-tommun-kd', f'choice ต้องเป็น {choice}; ห้าม mid/low')
    # Missing ROIC blocks spread/flag, not an independently calculable exact WACC.
    spread = roic-chosen if chosen is not None and roic is not None else None
    expect(w['book_wacc'],chosen,'18-tommun-spread','book_wacc')
    expect(w['spread'],spread,'18-tommun-spread','ROIC latest goodwill-inclusive - book WACC')
    expect(meta.get('book_wacc',NA),chosen,'18-tommun-spread','YAML book_wacc')
    yaml_spread = meta.get('roic_wacc_spread',NA)
    if isinstance(yaml_spread,str) and re.fullmatch(r'[+-]?[\d,]+(?:\.\d+)?\s+จุด',yaml_spread.strip()):
        yaml_spread = yaml_spread.strip().rsplit('จุด',1)[0].strip()
    expect(yaml_spread,spread,'18-tommun-spread','YAML spread')
    if w['flag'] != derived_flag or meta.get('roic_wacc_flag') != derived_flag:
        fail('18-tommun-spread', 'flag ต้อง derive จาก ROIC - WACC: '+derived_flag)
    verdict_pos = next((i for i,(n,_) in enumerate(heads) if n == 8), None)
    if verdict_pos is not None:
        verdict = '\n'.join(lines[heads[verdict_pos][1]:heads[verdict_pos+1][1] if verdict_pos+1 < len(heads) else len(lines)])
        match = re.search(r'ธง ROIC เทียบ book WACC\s*:\s*([^\n—·]+)([^\n]*)',verdict)
        if match and match.group(1).strip() != derived_flag:
            fail('18-tommun-spread', '§8 flag ต้องตรง derived flag: '+derived_flag)
        if match:
            number = re.search(r'spread\s+([^\s]+)',match.group(2),re.I)
            if number:
                expect(number.group(1),spread,'18-tommun-spread','§8 spread')
    for row in cash:
        a = parsed.get(row['FY'])
        if a is None:
            continue
        if not OFFICIAL.search(row['source']):
            fail('12-tommun-source','cash source ต้อง official')
        n = semantic_number(row['cash'],'cash',fail)
        ic,nopat = a['derived_ic'],a['derived_nopat']
        expect(row['IC_avg'],ic,'19-tommun-cash','cash IC_avg')
        expect(row['NOPAT'],nopat,'19-tommun-cash','cash NOPAT')
        valid_cash = n is not None and n >= 0 and ic is not None and ic > 0
        expect(row['cash_IC_pct'],n/ic*100 if valid_cash else None,'19-tommun-cash','cash / IC %')
        direction = 'N/A'
        if valid_cash and nopat is not None and ic-n > 0:
            direction = 'unchanged' if n == 0 or nopat == 0 else 'lower_positive' if nopat > 0 else 'less_negative'
        if row['direction'] != direction:
            fail('19-tommun-cash','cash-inclusive direction ต้องเป็น '+direction)
        if row['explanation'] != CASH_EXPLANATIONS[direction]:
            fail('19-tommun-cash','explanation ต้องเป็น '+CASH_EXPLANATIONS[direction])

SECTIONS = [
    (0, "SNAPSHOT & CAPITAL STRUCTURE"),
    (1, "INCOME STATEMENT & MARGINS"),
    (2, "BALANCE SHEET & SOLVENCY"),
    (3, "CASH FLOW"),
    (4, "QUALITY OF EARNINGS"),
    (5, "RETURN ON CAPITAL"),
    (6, "WORKING CAPITAL CYCLE"),
    (7, "CAPITAL ALLOCATION"),
    (8, "TOMMUN'S VERDICT"),
    (9, "PLAIN-LANGUAGE SUMMARY"),
    (10, "APPENDIX"),
]

PROFILE = Profile(
    semantic_check=check_semantics,
    extra_citation_patterns=(r'\[FRED\b[^\]]*\bDGS10\b[^\]]*\btier1\b[^\]]*\]',),
    slug="tommun",
    tool_name="tommun_check.py",
    required_yaml_fields=[
        "ticker", "company", "form", "fiscal_year", "accession", "filing_date",
        "as_of", "currency", "accounting_standard", "revenue_total",
        "tiers_used", "exec_summary",
        "book_wacc", "roic_wacc_spread", "roic_wacc_flag",
    ],
    enum_yaml_fields={
        "roic_wacc_flag": ("สร้างมูลค่าชัด", "ก้ำกึ่ง", "ทำลายมูลค่า", "N/A"),
    },
    # สืบทอดสายคะแนน/verdict จากโทนี่ + ปิดสายราคา/มูลค่าเพิ่ม
    # CAPM-only; no stock-price inputs anywhere.
    forbidden_yaml_fields=[
        "score", "conviction", "verdict", "rating", "recommendation",
        "target_price", "fair_value", "คะแนน",
        "price", "market_cap", "pe", "pe_ratio", "ev_ebitda", "valuation",
    ],
    sections=SECTIONS,
    appendix_section=10,
    appendix_tables=[
        TableSpec(
            key="source",
            label="ตารางที่มา (ตัวเลข | ฟอร์ม | งวด | Item)",
            short="ตารางที่มา",
            min_cols=4, max_cols=4,
            header_keys=("ฟอร์ม", "งวด"),
        ),
        TableSpec(
            key="calc",
            label="ตารางคำนวณ (ชื่อ | สูตร | ตัวตั้ง | ตัวหาร | ผล)",
            short="ตารางคำนวณ",
            min_cols=5, max_cols=None,
            header_keys=("สูตร", "ตัวตั้ง"),
            kind="calc",
        ),
        TableSpec(
            key="assumption",
            label="ตารางสมมติฐาน (สมมติฐาน | เหตุผล | กระทบตัวเลขไหน)",
            short="ตารางสมมติฐาน",
            min_cols=3, max_cols=3,
            header_keys=("สมมติฐาน", "เหตุผล"),
        ),
    ],
    # §5 ต้องประกาศสัดส่วนเงินสดเสมอ เพราะสูตร ROIC ที่ล็อกไว้ไม่หักเงินสด —
    # เครื่องตรวจไม่รู้ว่าเกิน 20% ไหม (ไม่มีงบดุลในมือ) แต่บังคับให้ "เขียนออกมา" ได้
    # ส่วน '+ เงินลงทุนระยะสั้น' เป็น optional เพราะบางบริษัทไม่แยกรายการนี้ในงบดุล
    section_required_patterns={
        # §3 สะพาน NI → OCF — เพิ่ม 2026-09-03 จากบทเรียนเมโม TER
        # เมโมนั้นสรุปว่า "OCF ทรงตัวเพราะเงินทุนหมุนเวียน" ทั้งที่ตัวเลขไม่ปิด: WC สวิง -96,385
        # ซึ่งใหญ่กว่าส่วนต่าง OCF ทั้งก้อน (+2,239) เพราะยังมีกำไรขายธุรกิจ 57,119 ที่ไม่เกิดซ้ำ
        # อยู่ในฐานปีก่อน — เมโมเจอตัวเลขนั้นเองใน §1 แต่ไม่ยกมาใช้ใน §3
        # เครื่องตรวจ "ไม่รู้" ว่าสะพานบวกกลับได้จริงไหม (ไม่มีงบในมือ) แต่บังคับให้ "เขียนออกมา" ได้
        # — ตรรกะเดียวกับบรรทัดสัดส่วนเงินสดด้านล่าง ส่วนวินัยว่ายอดต้องปิดอยู่ในพรอมต์ (วินัยตัวเลข ข้อ 7)
        3: [(
            r"สะพาน[^\n]{0,40}OCF",
            "สะพาน NI → OCF — บรรทัดหรือตารางที่ไล่จากกำไรสุทธิไป OCF (คำว่า 'สะพาน' + 'OCF')",
        )],
        5: [
            (
                r"เงินสด(?:\s*\+\s*เงินลงทุนระยะสั้น)?[^\n]*?\d+(?:\.\d+)?\s*%[^\n]*?ของสินทรัพย์รวม",
                "บรรทัดสัดส่วนเงินสด — 'เงินสด [+ เงินลงทุนระยะสั้น] ... X.XX% ของสินทรัพย์รวม'",
            ),
            # เพิ่ม 2026-09-03 จากบทเรียนเมโม TER เช่นกัน
            # เมโมนั้นรายงานเงินสด 7.70% ของ 'สินทรัพย์รวม' แล้วสรุปว่าไม่เข้าเกณฑ์ 20%
            # แต่สิ่งที่บิด ROIC คือเงินสดที่อยู่ใน 'ตัวหาร' คือ IC ซึ่งอยู่ที่ 14.56% (ใกล้เส้นกว่ามาก)
            # และปีฐานที่เอาไปเทียบ (FY2021) มีเงินสดถึง 54.62% ของ IC → ROIC 5 ปีเทียบกันไม่ได้
            (
                r"เงินสด[^\n]*?\d+(?:\.\d+)?\s*%[^\n]*?ของ\s*(?:invested\s+capital|IC)",
                "บรรทัดสัดส่วนเงินสดเทียบ IC — 'เงินสด ... X.XX% ของ invested capital (IC)' "
                "(ตัวหารที่ใช้ตัดสินเกณฑ์ 20% ต้องเป็น IC ไม่ใช่สินทรัพย์รวม)",
            ),
            # เพิ่ม 2026-09-23 — ตาราง WACC แบบบัญชีต้องอยู่ใน §5
            (
                r"book WACC",
                "ส่วน WACC แบบบัญชี — คำว่า 'book WACC' (ตาราง w · k_d · k_e ตามสูตรที่ล็อกไว้)",
            ),
        ],
        8: [(
            r"ธง ROIC เทียบ book WACC\s*:\s*(?:สร้างมูลค่าชัด|ก้ำกึ่ง|ทำลายมูลค่า|N/A)",
            "บรรทัดธง — 'ธง ROIC เทียบ book WACC: <สร้างมูลค่าชัด|ก้ำกึ่ง|ทำลายมูลค่า|N/A> — ...'",
        )],
        10: [POST_FILING_LINE],
    },
    # No market valuation/multiples anywhere, including appendix.
    # (คำอย่าง มูลค่าเหมาะสม · ราคาเป้าหมาย · upside · หุ้นถูก/แพง กฎ 3-verdict จับอยู่แล้ว ไม่ซ้ำ)

    forbidden_body_patterns=[
        (r"(?<![A-Za-z])P\s*/\s*E(?![A-Za-z])|\bPE ratio\b", "P/E"),
        (r"\bEV\s*/\s*(?:EBITDA|EBIT|Sales|Revenue|FCF)\b", "EV/EBITDA และตัวคูณ EV"),
        (r"(?<![A-Za-z])P\s*/\s*(?:S|B|FCF)(?![A-Za-z])", "P/S · P/B · P/FCF"),
        (r"\bmarket cap", "market cap"),
        (r"มูลค่าตลาดของ(?:บริษัท|หุ้น|กิจการ)", "มูลค่าตลาดของบริษัท/หุ้น"),
        (r"มูลค่าที่แท้จริง|\bintrinsic value\b", "มูลค่าที่แท้จริง / intrinsic value"),
        (r"ราคาหุ้น[^\n]{0,15}(?:ถูก|แพง)(?!" + r"ซื้อ|ขาย|ปรับ|กำหนด|บันทึก" + r")", "ราคาหุ้นถูก/แพง"),
        (r"(?:ซื้อขาย|เทรด)(?:กัน)?ที่\s*[\d.,]+\s*เท่า", "ซื้อขายที่ X เท่า"),
    ],
    forbidden_body_exempt_sections=(),
    # ธงต้องตรงกับเกณฑ์ของ spread และบรรทัดธง §8 ต้องพูดระดับ/ตัวเลขเดียวกับ YAML
    # (เพิ่ม 2026-09-23 หลัง /scrutinize พบว่าธงผิดระดับหรือขัดกับ §8 ก็ยัง PASS)
    # Semantic callback derives spread from inputs (not the supplied YAML flag).
    threshold_flag_check=None,
    # (0, 8) ไม่ใช่ (0, 9): §9 PLAIN-LANGUAGE SUMMARY ห้ามมีข้อเท็จจริงใหม่อยู่แล้ว
    # การบังคับ '(อนุมาน:)' ที่นั่นจึงขัดกับกฎของ section ตัวเอง — โทนี่/ร็อบกันหัวข้อสรุป
    # ออกจากกฎนี้เหมือนกัน (แก้ 2026-09-01 ให้สามโปรไฟล์ตรงกัน)
    opinion_sections=(0, 8),
    require_inference=True,
    assumption_table_key="assumption",
    rules_opinion_lines=[
        "2b-opinion   §0–§8 ทุกอันต้องมี 'สองบรรทัด' ปิดท้ายอยู่ในตัว section:",
        "             บรรทัดที่ขึ้นต้นด้วย '(อนุมาน:'  และบรรทัดที่ขึ้นต้นด้วย '(ความเห็น:'",
    ],
    rules_citation_lines=[
        "4-citation   ทุก 'แถว' ตารางนอก §10 ที่มีตัวเลขข้อเท็จจริง ต้องมี",
        "             [ฟอร์ม ... Item ...] หรือ [tier2]/[tier3] อยู่ในแถวนั้นเอง",
        "             หรือ [FRED DGS10 ... tier1 ...] สำหรับ macro-series citation (ไม่ต้องแต่ง SEC Item)",
        "             ยกเว้น: เลขลำดับล้วน 1–2 หลัก (คอลัมน์ #) และแถวที่มี",
        "             [ไม่เปิดเผย]/[ข้อมูลไม่พอ]",
    ],
    rules_appendix_lines=[
        "7-appendix   §10 ต้องมี 3 ตาราง: ที่มา = 4 ช่อง (ตัวเลข|ฟอร์ม|งวด|Item) ·",
        "             คำนวณ = 5 ช่อง (ชื่อ|สูตร|ตัวตั้ง|ตัวหาร|ผล) ·",
        "             สมมติฐาน = 3 ช่อง (สมมติฐาน|เหตุผล|กระทบตัวเลขไหน) ห้ามมีช่องว่าง",
        "             จำนวนช่องคือตัวจำแนกตาราง — ตารางอื่นในภาคผนวกจะถูกอ่านผิดกลุ่ม",
        "             + บรรทัด เหตุการณ์หลัง filing: <กระทบ|ไม่กระทบ|ไม่มี 8-K|ไม่มี 6-K> (2c-required-line)",
    ],
    rules_extra_lines=[
        "             วงเล็บ (= ...) คิดได้ทั้ง + − × ÷ และวงเล็บซ้อน เช่น",
        "               NOPAT       93,188.26 (=123,216×0.7563)",
        "               IC เฉลี่ย    250,000 (=(240,000+260,000)÷2)",
        "             แถวที่ไม่ใช่การหาร (คูณ/บวก) ให้ใส่ตัวหาร = 1 แล้วผลเท่ากับตัวตั้ง",
        "             ปัดเศษได้เท่าหลักทศนิยมที่เขียนไว้เอง (เขียน 2 ตำแหน่ง = คลาด 0.005)",
        "12-tommun-schema §5 ต้องมี ### AUDIT ANNUAL / AUDIT WACC / AUDIT CASH (Markdown tables; ไม่ใช่ YAML blob)",
        "             ANNUAL headers: " + " | ".join(ANNUAL_HEADERS),
        "             WACC headers: field | value | source | unit | as_of | coverage",
        "             WACC fields: " + " | ".join(WACC_FIELDS),
        "             CASH headers: " + " | ".join(CASH_HEADERS),
        "             ปี FYyyyy ห้ามซ้ำ; CASH ครบทุกปี ANNUAL; WACC ปีล่าสุด",
        "12-tommun-source official filing citation สำหรับ annual/book/debt; Rf=FRED DGS10 tier1; industry_beta/ERP=Damodaran tier3; unit และ ISO as_of ห้ามว่าง",
        "13-tommun-number finite Decimal ทั้งช่อง (comma grouping ถูกต้อง; % optional); NA = [ข้อมูลไม่พอ]; ห้าม junk/NaN/Infinity",
        "14-tommun-capm k_e = Rf + industry_beta × ERP คิดซ้ำ (Rf/ERP/ke หน่วย percent; beta dimensionless)",
        "             industry_beta coverage: Industry group: <ชื่อกลุ่มอุตสาหกรรม> ไม่ใช่ company/stock beta",
        "14-tommun-method ห้าม averaging/Gordon/debt-plus/P0/stock-price/GDP/get_price_history ทุก section รวม appendix; routing/ข้อความห้ามใช้ไม่ใช่ input",
        "15-tommun-tax ETR = tax_provision / pretax ×100; pretax>0 และ ETR 0..50 inclusive ใช้ effective; นอกนั้น statutory จาก official tax note เท่านั้น",
        "             statutory tax_source ต้องอ้าง FY ของแถว; statutory21 ห้าม default; unavailable → dependent NA; latest T_used ใช้ debt shield ด้วย",
        "             unknown pretax หรือ pretax>0/provision missing ไม่ยืนยัน fallback trigger → T_used/NOPAT และผลที่พึ่งภาษี NA",
        "16-tommun-book w_D/P/E จาก book สิ้นปี; D ไม่รวม leases; ICavg = average(D+P+E+operating leases) ไม่หัก cash/goodwill",
        "             D=0,P>0 ยังรวม preferred; E<=0 → weights/bookWACC/spread NA, flag N/A",
        "             numeric k_p ต้อง official filing; missing beginning balance → dependent averages NA; missing ROIC ไม่ลบ exact WACC ที่คำนวณได้",
        "             E<=0 ไม่ต้องดึง CAPM inputs; value NA อนุญาต source/as_of N/A แต่ unit/coverage blocker ยังต้องระบุ; k_p unavailable → WACC/spread NA",
        "17-tommun-kd accrual interest_expense/D_avg; ห้าม cash-interest/debt และ partial coupon proxy",
        "             missing interest,D>0: kd_lower=0; kd_upper=max effective_rate; ### AUDIT DEBT headers: instrument | balance | effective_rate | source",
        "             ทุก tranche มี official citation; sum balance = D = debt_coverage_amount; coverage ของ kd_upper = all interest-bearing debt excluding leases",
        "             คิด WACC_low/high และ spread_low/high; ธงเหมือนกันเลือก high conservatively; ต่างกัน/ไม่มี upper → bookWACC/spread [ข้อมูลไม่พอ], flag/choice N/A; ห้าม mid/low",
        "             flag_low=flag(ROIC-WACC_low)=flag(spread_high); flag_high=flag(ROIC-WACC_high)=flag(spread_low); no bounds → endpoint flags N/A",
        "             endpoint arithmetic ใช้ max effective_rate ของ AUDIT DEBT ก่อนปัดเศษ ไม่ใช้ displayed kd_upper จนธงผิด",
        "18-tommun-spread derive latest goodwill-inclusive ROIC-WACC; >5 สร้างมูลค่าชัด,0..5 ก้ำกึ่ง,<0 ทำลายมูลค่า; YAML และ §8 ต้องตรง",
        "19-tommun-cash cash_IC_pct = cash/ICavg×100; cash-inclusive direction: positive NOPAT lower_positive / negative less_negative / zero unchanged",
        "             invalid IC or IC-cash denominator → direction N/A (ไม่ assert ทิศ); ทุกปีมี row",
        "             explanation exact canonical: " + " / ".join(CASH_EXPLANATIONS.values()),
        "20-tommun-roic-trend AUDIT CASH ปีฐานเทียบปีล่าสุดต่างกัน > 15 จุด → exec_summary/§8/§9 ห้ามมีวลีแนวโน้ม",
        "             ข้ามปีที่ประธานคือ ROIC/ผลตอบแทน (ต่ำสุด/สูงสุดใน N ปี · ลดลงต่อเนื่อง/เรื่อย ๆ · แนวโน้มลดลง)",
        "             เว้นแต่กำกับ 'หักเงินสด' ระหว่าง ROIC กับวลี · วลีปีต่อปี (ลดจาก/ลดเหลือ) ใช้ปีที่อ้างหรือปีก่อนหน้า",
        "             ROIC ตัด goodwill ไม่นับเป็นคำกำกับ (ตัวหารยังมีเงินสด) · ประโยค 'ไม่ได้แปลว่า ...' ไม่นับ",
        "9-assumption ทุก [สมมติฐาน: ...] ที่เขียนในเนื้อเมโม (§0–§9) ต้องมีแถวรองรับใน",
        "             ตารางสมมติฐาน §10 — จำนวนแถวต้องไม่น้อยกว่าจำนวนจุดที่กำกับไว้",
    ],
)
