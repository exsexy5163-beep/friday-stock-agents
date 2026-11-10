"""Option B regression tests; synthetic data only, scratch tempfiles cleaned."""
import os
import re
import json
import subprocess
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
from tools.memocheck.core import check_memo
from tools.memocheck.profiles.tommun import PROFILE

ROOT = Path(__file__).resolve().parents[2]
SOURCE = '[10-K FY2025, Item 8, synthetic fixture]'
TAX_SOURCE = '[10-K FY2025, Item 8, Tax note, synthetic fixture]'
NA = '[ข้อมูลไม่พอ]'
ANNUAL = 'FY pretax tax_provision ETR statutory T_used EBIT D_begin P_begin E_begin leases_begin D_end P_end E_end leases_end IC_avg NOPAT ROIC source tax_source'.split()
WACC = 'FY D P E D_avg interest_expense T_used Rf industry_beta ERP k_e k_p w_d w_p w_e k_d kd_lower kd_upper WACC_low WACC_high spread_low spread_high flag_low flag_high book_wacc spread flag choice debt_coverage_amount'.split()
CASH = 'FY cash IC_avg NOPAT cash_IC_pct direction explanation source'.split()
EXPLANATIONS = dict(lower_positive='กด ROIC บวกให้ต่ำลง',less_negative='ทำให้ ROIC ติดลบน้อยลง',unchanged='ROIC ไม่เปลี่ยน', **{'N/A':'ไม่สรุปทิศทาง'})

def flag(v):
    return 'สร้างมูลค่าชัด' if v > 5 else 'ก้ำกึ่ง' if v >= 0 else 'ทำลายมูลค่า'

def table(headers, rows):
    return '| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(['---'] * len(headers)) + ' |\n' + ''.join('| ' + ' | '.join(str(row[k]) for k in headers) + ' |\n' for row in rows)

def model(**changes):
    a: dict = dict(zip(ANNUAL, ['FY2025',19000,3800,20,21,20,20000,25000,0,55000,10000,30000,0,60000,10000,95000,16000,'16.8421052632',SOURCE,TAX_SOURCE]))
    a.update(changes.pop('annual', {}))
    w: dict = dict.fromkeys(WACC, NA)
    w.update(FY=a['FY'], D=a['D_end'], P=a['P_end'], E=a['E_end'], D_avg=27500, interest_expense=1000, T_used=a['T_used'], Rf=4, industry_beta='1.2', ERP=5, k_e=10, k_p=0, w_d='33.3333333333', w_p=0, w_e='66.6666666667', k_d='3.63636363636', choice='exact', debt_coverage_amount=30000)
    w.update(changes.pop('wacc', {}))
    c: dict = dict(FY=a['FY'], cash=12000, IC_avg=a['IC_avg'], NOPAT=a['NOPAT'], cash_IC_pct='12.6315789474', direction='lower_positive', source=SOURCE)
    c.update(changes.pop('cash', {}))
    c.setdefault('explanation',EXPLANATIONS.get(c['direction'],'wrong'))
    if D(str(w['E'])) <= 0:
        w.update(w_d=NA,w_p=NA,w_e=NA)
    exact_roic = D(str(a['NOPAT']))/D(str(a['IC_avg']))*100 if a['NOPAT'] != NA and D(str(a['IC_avg'])) > 0 else None
    if D(str(w['E'])) > 0 and w['T_used'] != NA and a['ROIC'] != NA:
        den = D(str(w['D'])) + D(str(w['P'])) + D(str(w['E']))
        def wa(kd):
            return (D(str(w['D'])) * kd * (1-D(str(w['T_used']))/100) + D(str(w['P']))*D(str(w['k_p'])) + D(str(w['E']))*D(str(w['k_e']))) / den
        if w['interest_expense'] == NA and w['kd_upper'] != NA:
            lo, hi = wa(D(0)), wa(D(str(w['kd_upper'])))
            w.update(WACC_low=str(lo), WACC_high=str(hi), spread_low=str(exact_roic-hi), spread_high=str(exact_roic-lo))
            stable = flag(D(w['spread_low'])) == flag(D(w['spread_high']))
            w.update(flag_low=flag(D(w['spread_high'])),flag_high=flag(D(w['spread_low'])))
            w.update(book_wacc=str(hi) if stable else NA, spread=w['spread_low'] if stable else NA, flag=flag(D(w['spread_low'])) if stable else 'N/A', choice='high' if stable else 'N/A')
        elif w['interest_expense'] != NA or D(str(w['D'])) == 0:
            exact_kd = D(str(w['interest_expense']))/D(str(w['D_avg']))*100 if D(str(w['D'])) else D(0)
            v = wa(exact_kd)
            w.update(book_wacc=str(v), spread=str(exact_roic-v), flag=flag(exact_roic-v))
        else:
            w.update(flag='N/A', choice='N/A')
    else:
        w.update(flag='N/A', choice='N/A')
    if w['flag_low'] == NA:
        w.update(flag_low='N/A',flag_high='N/A')
    w.update(changes.pop('results', {}))
    return a, w, c

def memo(a=None, w=None, c=None, debt=None, prior=()):
    if a is None:
        a, w, c = model()
    base = (ROOT / 'scratch/tommun-check-fixtures/good.md').read_text()
    base = re.sub(r'^book_wacc:.*$', 'book_wacc: "' + str(w['book_wacc']) + '"', base, flags=re.M)
    base = re.sub(r'^roic_wacc_spread:.*$', 'roic_wacc_spread: "' + str(w['spread']) + '"', base, flags=re.M)
    base = re.sub(r'^roic_wacc_flag:.*$', 'roic_wacc_flag: ' + w['flag'], base, flags=re.M)
    base = re.sub(r'ธง ROIC เทียบ book WACC:[^\n]*', 'ธง ROIC เทียบ book WACC: ' + w['flag'], base)
    sources = dict(Rf='[FRED DGS10, tier1, synthetic fixture]',industry_beta='[tier3] Damodaran industry beta, synthetic fixture',ERP='[tier3] Damodaran ERP, synthetic fixture')
    wr = [dict(field=k, value=v, source=sources.get(k,SOURCE), unit='USD million / percent / dimensionless', as_of='2025-10-31', coverage='all interest-bearing debt excluding leases' if k=='kd_upper' else 'Industry group: industrial equipment' if k=='industry_beta' else 'not applicable') for k,v in w.items()]
    chunk = '\n## §5 RETURN ON CAPITAL\n\nเงินสด 8.00% ของสินทรัพย์รวม · เงินสด 12.63% ของ IC\nbook WACC\n\n### AUDIT ANNUAL\n' + table(ANNUAL,[*(p[0] for p in prior),a]) + '\n### AUDIT WACC\n' + table('field value source unit as_of coverage'.split(),wr) + '\n### AUDIT CASH\n' + table(CASH,[*(p[1] for p in prior),c])
    if debt is not None:
        chunk += '\n### AUDIT DEBT\n' + table('instrument balance effective_rate source'.split(),debt)
    chunk += '\n(อนุมาน: ทดสอบ)\n(ความเห็น: ทดสอบ)\n\n'
    return re.sub(r'\n## §5 .*?(?=## §6 )',chunk,base,flags=re.S)

def cash_years(*cash_by_year):
    """Annual rows FY2021.. with identical arithmetic; only cash (and so cash % of IC) differs by year."""
    *older, latest = cash_by_year
    a, w, c = model(cash=dict(cash=latest, cash_IC_pct=str(D(latest)/95000*100)))
    prior = []
    for fy, cash in zip(['FY2021','FY2022','FY2023','FY2024'], older):
        prior.append((dict(a, FY=fy, tax_source=TAX_SOURCE.replace('FY2025', fy)),
                      dict(c, FY=fy, cash=cash, cash_IC_pct=str(D(cash)/95000*100))))
    return memo(a, w, c, prior=prior)

EXEC_ROIC = '  - ROIC ตามสูตรที่ล็อกไว้ 16.84% ตัด goodwill ออกแล้วเป็น 20.00%'
S8_ANCHOR = 'เงินค้างอยู่ที่ลูกหนี้และสินค้าคงเหลือที่โตเร็วกว่ารายได้'
S9_ANCHOR = '- ทุก 100 บาทที่ขายได้ เหลือเป็นกำไรจากการดำเนินงาน 20 บาท'

def claim(text, where, sentence):
    if where == 'exec':
        return text.replace(EXEC_ROIC, '  - ' + sentence, 1)
    anchor = S8_ANCHOR if where == '§8' else S9_ANCHOR
    return text.replace(anchor, anchor + '\n' + sentence, 1)

class TommunSemantics(unittest.TestCase):
    def check_text(self, text):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', dir=ROOT / 'scratch', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            return check_memo(str(f.name), PROFILE)

    def test_missing_audit_tables(self):
        code, failures = self.check_text(memo().replace('AUDIT ANNUAL', 'missing annual'))
        self.assertEqual(code, 1)
        self.assertTrue(any('[12-tommun-schema]' in f for f in failures), failures)

    def assert_rule(self, text, rule):
        code, failures = self.check_text(text)
        self.assertEqual(code, 1, failures)
        self.assertTrue(any('[' + rule + ']' in f for f in failures), failures)

    def test_canonical_pass(self):
        self.assertEqual(self.check_text(memo()), (0, []))
        self.assertEqual(check_memo(str(ROOT/'scratch/tommun-check-fixtures/good.md'),PROFILE),(0,[]))

    def test_capm_recompute(self):
        self.assert_rule(memo(*model(wacc={'k_e':11})), '14-tommun-capm')

    def test_finite_strict_numbers(self):
        for value in ['NaN','Infinity','-Infinity','10junk','1e999999999','1,2','--2']:
            with self.subTest(value=value):
                self.assert_rule(memo().replace('| Rf | 4 |','| Rf | '+value+' |'), '13-tommun-number')

    def test_prohibited_methods_global(self):
        for value in ['P0 = 10','stock price = 10','ราคาหุ้น 10 USD','GDP = 3%','get_price_history','k_e = Gordon','k_e = debt-plus-risk','k_e = หนี้บวกส่วนเพิ่ม','k_e เฉลี่ย 2 วิธี','k_e = (CAPM + Gordon)/2']:
            with self.subTest(value=value):
                self.assert_rule(memo()+'\n'+value, '14-tommun-method')

    def test_routing_and_nonprice_shares_allowed(self):
        self.assertEqual(self.check_text(memo()+'\nส่งต่อ Damon เรื่องราคาหุ้น; ไม่ใช้ Gordon หรือ GDP\nหุ้น 1,000 ล้านหุ้น ซื้อหุ้นคืน 8,000 ลบ.USD\n'), (0, []))
        self.assertEqual(self.check_text(memo()+'\nCrowdStrike รับรู้รายได้เฉลี่ยตามอายุสัญญา 1–3 ปี\nทดสอบขอบเขต k_d ไม่ได้ใช้เงินสดจ่ายดอกเบี้ย ÷ หนี้ ตามกฎ\n'),(0,[]))
        self.assertEqual(self.check_text(memo()+'\nROIC ตัด LT marketable securities จาก IC เฉลี่ย\nk_d [ไม่เปิดเผย] เงินสดจ่ายดอกเบี้ย ไม่ใช้แทน\n'),(0,[]))

    def test_tax_boundaries(self):
        for pretax, provision, etr, used in [(100,0,0,0),(100,50,50,50),(0,0,NA,21),(-100,20,-20,21),(100,-1,-1,21),(100,51,51,21)]:
            with self.subTest(pretax=pretax, provision=provision):
                n = D(20000)*(1-D(used)/100)
                a,w,c = model(annual=dict(pretax=pretax,tax_provision=provision,ETR=etr,T_used=used,NOPAT=str(n),ROIC=str(n/D(95000)*100)))
                self.assertEqual(self.check_text(memo(a,w,c)), (0, []))
                a['T_used'] = 22
                self.assert_rule(memo(a,w,c), '15-tommun-tax')

    def test_tax_source_and_unavailable(self):
        a,w,c = model(annual=dict(pretax=0,ETR=NA,T_used=21,NOPAT=15800,ROIC=str(D(15800)/95000*100)))
        a['tax_source'] = '[tier2]'
        self.assert_rule(memo(a,w,c),'15-tommun-tax')
        a,w,c = model(annual=dict(pretax=0,ETR=NA,statutory=NA,T_used=NA,NOPAT=NA,ROIC=NA),cash=dict(NOPAT=NA,direction='N/A'))
        self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))

    def test_book_weights_and_ic(self):
        self.assert_rule(memo(*model(wacc={'w_d':30})), '16-tommun-book')
        self.assert_rule(memo(*model(annual={'IC_avg':85000})), '16-tommun-book')
        self.assert_rule(memo(*model(wacc={'D':40000})), '16-tommun-book')

    def test_debt_zero_preferred(self):
        a,w,c = model(annual=dict(D_begin=0,D_end=0,P_begin=10000,P_end=10000,E_begin=80000,E_end=80000,IC_avg=100000,ROIC=16),wacc=dict(D=0,P=10000,E=80000,D_avg=0,interest_expense=NA,k_d=0,k_p=6,w_d=0,w_p=str(D(100)/9),w_e=str(D(800)/9)),cash=dict(IC_avg=100000,cash_IC_pct=12))
        self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))
        w['book_wacc']='10.00'
        self.assert_rule(memo(a,w,c),'18-tommun-spread')

    def test_nonpositive_equity(self):
        for equity in [0,-1]:
            a,w,c = model(wacc={'E':equity},annual={'E_end':equity,'IC_avg':str((D(90000)+D(40000)+equity)/2)})
            a['ROIC']=str(D(a['NOPAT'])/D(a['IC_avg'])*100)
            c.update(IC_avg=a['IC_avg'],cash_IC_pct=str(D(12000)/D(a['IC_avg'])*100))
            w['w_d']=w['w_p']=w['w_e']=NA
            self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))
            w['book_wacc']=10
            self.assert_rule(memo(a,w,c),'18-tommun-spread')

    def test_kd_bounds_stable_flip(self):
        debt=[dict(instrument='all debt tranche',balance=30000,effective_rate=6,source=SOURCE)]
        for ebit in [20000,9500]:
            n=D(ebit)*D('.8')
            a,w,c=model(annual=dict(EBIT=ebit,NOPAT=str(n),ROIC=str(n/95000*100)),wacc=dict(interest_expense=NA,k_d=NA,kd_lower=0,kd_upper=6))
            if ebit == 9500:
                self.assertEqual(w['book_wacc'],NA)
                self.assertEqual(w['spread'],NA)
                self.assertEqual(w['flag'],'N/A')
                self.assertEqual(w['flag_low'],'ก้ำกึ่ง')
                self.assertEqual(w['flag_high'],'ทำลายมูลค่า')
            else:
                self.assertEqual(w['choice'],'high')
                self.assertEqual(w['flag'],'สร้างมูลค่าชัด')
            self.assertEqual(self.check_text(memo(a,w,c,debt)),(0,[]))
            w['choice']='mid'
            self.assert_rule(memo(a,w,c,debt),'17-tommun-kd')

    def test_missing_kd_upper_and_partial_coverage(self):
        a,w,c=model(wacc=dict(interest_expense=NA,k_d=NA))
        self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))
        a,w,c=model(wacc=dict(interest_expense=NA,k_d=NA,kd_lower=0,kd_upper=6))
        for balance in [10000,29999]:
            self.assert_rule(memo(a,w,c,[dict(instrument='partial coupon',balance=balance,effective_rate=6,source=SOURCE)]),'17-tommun-kd')
        self.assert_rule(memo(a,w,c).replace('| interest_expense | [ข้อมูลไม่พอ] |','| interest_expense | cash interest / debt |'),'13-tommun-number')

    def test_cash_three_signs_invalid_denominator(self):
        for ebit,direction in [(20000,'lower_positive'),(-20000,'less_negative'),(0,'unchanged')]:
            n=D(ebit)*D('.8')
            a,w,c=model(annual=dict(EBIT=ebit,NOPAT=str(n),ROIC=str(n/95000*100)),cash=dict(direction=direction))
            self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))
            c['direction']='wrong'
            self.assert_rule(memo(a,w,c),'19-tommun-cash')
        a,w,c=model(annual=dict(D_begin=0,E_begin=-10000,D_end=0,E_end=-10000,IC_avg=0,ROIC=NA),wacc=dict(D=0,E=-10000,D_avg=0,k_d=0),cash=dict(IC_avg=0,cash_IC_pct=NA,direction='N/A'))
        self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))

    def test_wrong_spread_and_flag_derived(self):
        self.assert_rule(memo(*model(results=dict(spread=7.84))), '18-tommun-spread')
        self.assert_rule(memo(*model(results=dict(flag='ก้ำกึ่ง'))), '18-tommun-spread')

    def test_missing_provenance(self):
        for source in ['none','[FRED DGS2, tier1]','[FRED DGS10, tier3]']:
            self.assert_rule(memo().replace('[FRED DGS10, tier1, synthetic fixture]',source),'12-tommun-source')

    def test_cli_direct_parity(self):
        for text in [memo(),memo(*model(wacc={'k_e':11}))]:
            with tempfile.NamedTemporaryFile(mode='w',suffix='.md',dir=ROOT/'scratch',encoding='utf-8') as f:
                f.write(text); f.flush()
                code, failures=check_memo(f.name,PROFILE)
                p=subprocess.run([str(ROOT/'.venv-utils/bin/python'),'tools/tommun_check.py',f.name],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True)
                self.assertEqual(p.returncode,code)
                for failure in failures:
                    self.assertIn(failure,p.stdout)

    @unittest.skip("ต้องใช้ไฟล์ baseline ส่วนตัวที่ไม่ได้เผยแพร่")
    def test_other_profiles_baseline(self):
        from tools.memocheck.profiles import load
        cases=json.loads((ROOT/'scratch/tommun-check-fixtures/cases.json').read_text())
        manifest=json.loads((ROOT/cases['baseline_manifest']).read_text())
        self.assertEqual(set(cases['generated_tests']),{name for name in dir(type(self)) if name.startswith('test_')})
        for case in cases['legacy']:
            code,failures=check_memo(str(ROOT/case['path']),PROFILE)
            self.assertEqual(code,case['expected_exit'])
            for rule in case['required_rule_ids']:
                self.assertTrue(any('['+rule+']' in f for f in failures),case['path'])
        for slug in ['tony','rob','adam','damon']:
            for case in manifest['baseline'][slug]:
                with self.subTest(slug=slug,path=case['path']):
                    self.assertEqual(check_memo(str(ROOT/case['path']),load(slug)),(case['exit'],case['failures']))
        from contextlib import redirect_stdout
        from io import StringIO
        from tools.memocheck.core import print_rules
        for slug in ['tony','rob','adam','damon']:
            stream=StringIO()
            with redirect_stdout(stream):
                print_rules(load(slug))
            self.assertEqual(stream.getvalue(),manifest['baseline_rules'][slug])

    def test_yaml_nonfinite_junk_and_s8(self):
        for value in ['.nan','.inf','-.inf','"10junk"','"NaN"','true']:
            with self.subTest(value=value):
                text=re.sub(r'^roic_wacc_spread:.*$', 'roic_wacc_spread: '+value,memo(),flags=re.M)
                self.assert_rule(text,'13-tommun-number')
        self.assert_rule(memo().replace('ธง ROIC เทียบ book WACC: สร้างมูลค่าชัด','ธง ROIC เทียบ book WACC: ทำลายมูลค่า'),'18-tommun-spread')
        self.assert_rule(memo().replace('ธง ROIC เทียบ book WACC: สร้างมูลค่าชัด','ธง ROIC เทียบ book WACC: สร้างมูลค่าชัด — spread 99.00'),'18-tommun-spread')

    def test_no_blanket_negation_escape(self):
        self.assert_rule(memo()+'\nไม่ใช้ Gordon แต่ใช้ stock price = 10','14-tommun-method')
        self.assert_rule(memo()+'\nGordon dividend-growth method ใช้คำนวณต้นทุนทุน','14-tommun-method')
        self.assert_rule(memo()+'\nk_d = cash interest / debt','17-tommun-kd')

    def test_statutory_requires_tax_note_even_if_unused(self):
        a,w,c=model(annual={'tax_source':'[tier2]'})
        self.assert_rule(memo(a,w,c),'15-tommun-tax')

    def test_missing_required_numeric_inputs(self):
        for field in ['pretax','tax_provision','EBIT','E_begin','E_end']:
            a,w,c=model()
            a[field]=NA
            self.assert_rule(memo(a,w,c),'15-tommun-tax' if field in ('pretax','tax_provision','EBIT') else '16-tommun-book')

    def test_schema_duplicate_and_location(self):
        text=memo()
        self.assert_rule(text.replace('### AUDIT CASH','### AUDIT CASH\n\n### AUDIT CASH'),'12-tommun-schema')
        self.assert_rule(text.replace('| FY | FY2025 |','| D | FY2025 |'),'12-tommun-schema')
        self.assert_rule(text.replace('### AUDIT ANNUAL','## §55 AUDIT ANNUAL'),'12-tommun-schema')

    def test_endpoint_flags(self):
        a,w,c=model(wacc=dict(interest_expense=NA,k_d=NA,kd_lower=0,kd_upper=6))
        debt=[dict(instrument='all debt',balance=30000,effective_rate=6,source=SOURCE)]
        for field in ['flag_low','flag_high']:
            wrong=dict(w); wrong[field]='ทำลายมูลค่า'
            self.assert_rule(memo(a,wrong,c,debt),'17-tommun-kd')

    def test_tax_note_corresponding_fy(self):
        self.assert_rule(memo(*model(annual={'tax_source':'[10-K FY2024, Item 8, Tax note]'})),'15-tommun-tax')

    def test_industry_group_not_company_beta(self):
        for coverage in ['not applicable','company beta','stock beta','industry:']:
            text=memo().replace('Industry group: industrial equipment',coverage)
            self.assert_rule(text,'14-tommun-capm')

    def test_cash_prose_must_match_enum(self):
        for ebit,direction in [(20000,'lower_positive'),(-20000,'less_negative'),(0,'unchanged')]:
            n=D(ebit)*D('.8')
            a,w,c=model(annual=dict(EBIT=ebit,NOPAT=str(n),ROIC=str(n/95000*100)),cash=dict(direction=direction,explanation='opposite'))
            self.assert_rule(memo(a,w,c),'19-tommun-cash')

    def test_gated_missing_capm_sources(self):
        a,w,c=model(wacc={'E':0},annual={'E_end':0,'IC_avg':65000},cash=dict(IC_avg=65000,cash_IC_pct=str(D(12000)/65000*100)))
        a['ROIC']=str(D(16000)/65000*100)
        for key in ['Rf','industry_beta','ERP','k_e']:
            w[key]=NA
        text=memo(a,w,c)
        for key in ['Rf','industry_beta','ERP','k_e']:
            text=re.sub(r'^\| '+key+r' \|.*$', '| '+key+' | '+NA+' | N/A | declared input unit | N/A | E<=0 gate; no retrieval |',text,flags=re.M)
        self.assertEqual(self.check_text(text),(0,[]))
        self.assert_rule(text.replace(TAX_SOURCE,'[tier3]'),'15-tommun-tax')

    def test_preferred_missing_cost_dependent_na(self):
        a,w,c=model(annual=dict(P_begin=10000,P_end=10000,E_begin=45000,E_end=50000),wacc=dict(P=10000,E=50000,w_p=str(D(100)/9),w_e=str(D(500)/9)))
        w.update(k_p=NA,book_wacc=NA,spread=NA,flag='N/A',choice='N/A')
        self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))
        w['k_p']=-1
        self.assert_rule(memo(a,w,c),'16-tommun-book')

    def test_flag_boundaries_use_unrounded_spread(self):
        for ebit,roic,wanted in [('12500','10','ก้ำกึ่ง'),('18750','15','ก้ำกึ่ง'),('18750.00125','15.000001','สร้างมูลค่าชัด'),('12499.99875','9.999999','ทำลายมูลค่า')]:
            nopat=str(D(ebit)*D('.8'))
            a,w,c=model(annual=dict(EBIT=ebit,NOPAT=nopat,ROIC=roic,D_begin=0,D_end=0,E_begin=90000,E_end=90000,IC_avg=100000),wacc=dict(D=0,E=90000,D_avg=0,interest_expense=NA,k_d=0,w_d=0,w_p=0,w_e=100),cash=dict(IC_avg=100000,cash_IC_pct=12))
            self.assertEqual(w['flag'],wanted)
            self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))
            w['flag']='N/A'
            self.assert_rule(memo(a,w,c),'18-tommun-spread')

    def test_rounded_debt_bound_cannot_change_flag(self):
        a,w,c=model(annual=dict(EBIT='9856.25',NOPAT=7885,ROIC='8.30'),wacc=dict(interest_expense=NA,k_d=NA,kd_lower=0,kd_upper=6))
        debt=[dict(instrument='all debt',balance=30000,effective_rate='6.49',source=SOURCE)]
        self.assert_rule(memo(a,w,c,debt),'17-tommun-kd')
        a,w,c=model(annual=dict(EBIT='9856.25',NOPAT=7885,ROIC='8.30'),wacc=dict(interest_expense=NA,k_d=NA,kd_lower=0,kd_upper='6.49'))
        self.assertEqual(w['flag'],'N/A')
        self.assertEqual(self.check_text(memo(a,w,c,debt)),(0,[]))

    def test_missing_beginning_balance_propagates_na(self):
        a,w,c=model()
        a.update(D_begin=NA,IC_avg=NA,ROIC=NA)
        w.update(D_avg=NA,k_d=NA,book_wacc=NA,spread=NA,flag='N/A',choice='N/A')
        c.update(IC_avg=NA,cash_IC_pct=NA,direction='N/A',explanation=EXPLANATIONS['N/A'])
        self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))

    def test_documented_yaml_spread_unit(self):
        text=re.sub(r'^roic_wacc_spread:.*$', 'roic_wacc_spread: "+9.21 จุด"',memo(),flags=re.M)
        self.assertEqual(self.check_text(text),(0,[]))
        self.assert_rule(text.replace('+9.21 จุด','+99.21 จุด'),'18-tommun-spread')

    def test_preferred_rate_requires_official_filing(self):
        a,w,c=model(annual=dict(D_begin=0,D_end=0,P_begin=10000,P_end=10000,E_begin=80000,E_end=80000,IC_avg=100000,ROIC=16),wacc=dict(D=0,P=10000,E=80000,D_avg=0,interest_expense=NA,k_d=0,k_p=6,w_d=0,w_p=str(D(100)/9),w_e=str(D(800)/9)),cash=dict(IC_avg=100000,cash_IC_pct=12))
        text=memo(a,w,c).replace('| k_p | 6 | '+SOURCE,'| k_p | 6 | [tier3] invented contractual rate')
        self.assert_rule(text,'12-tommun-source')

    def test_unknown_pretax_does_not_trigger_statutory(self):
        a,w,c=model()
        a.update(pretax=NA,ETR=NA)
        self.assert_rule(memo(a,w,c),'15-tommun-tax')
        a.update(T_used=NA,NOPAT=NA,ROIC=NA)
        w.update(T_used=NA,book_wacc=NA,spread=NA,flag='N/A',choice='N/A')
        c.update(NOPAT=NA,direction='N/A',explanation=EXPLANATIONS['N/A'])
        self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))

    def test_missing_roic_retains_calculable_wacc(self):
        a,w,c=model()
        a.update(EBIT=NA,NOPAT=NA,ROIC=NA)
        w.update(spread=NA,flag='N/A',choice='exact')
        c.update(NOPAT=NA,direction='N/A',explanation=EXPLANATIONS['N/A'])
        self.assertEqual(self.check_text(memo(a,w,c)),(0,[]))

    def test_proxy_warning_cannot_disable_method_bans(self):
        for clause in ['P0 = 10 ไม่ใช้แทน','k_e = Gordon ไม่ใช้แทน']:
            self.assert_rule(memo()+'\n'+clause,'14-tommun-method')
        self.assert_rule(memo()+'\nk_d = cash interest / debt ไม่ใช้แทน','17-tommun-kd')

    def test_roic_trend_cash_gap_fails_outside_s5(self):
        # FY2021 เงินสด 1% ของ IC · FY2025 20% → ต่างกัน 19 จุด (เคสจริง BWXT 2.03% → 18.34%)
        base = cash_years(950, 19000)
        self.assertEqual(self.check_text(base), (0, []))
        for where, sentence in [
            ('exec', 'ROIC (รวม goodwill) FY2025 ต่ำสุดในห้าปี'),
            ('§9', '- ผลตอบแทนจากเงินที่ลงไปลดลงเรื่อย ๆ'),
            ('§8', 'ROIC ลดลงต่อเนื่องทุกปี'),
            ('§8', 'ROIC (ตัด goodwill) แนวโน้มลดลง'),
            ('exec', 'ROIC FY2025 ลดจาก FY2021 ชัดเจน'),
            ('§9', '- ROIC is the lowest in five years'),
        ]:
            with self.subTest(where=where, sentence=sentence):
                self.assert_rule(claim(base, where, sentence), '20-tommun-roic-trend')

    def test_roic_trend_allowed_sentences(self):
        base = cash_years(950, 19000)
        for where, sentence in [
            ('exec', 'ROIC หักเงินสดออกจาก IC FY2025 ต่ำสุดในห้าปี'),
            ('§9', '- ผลตอบแทน (คิดแบบไม่นับเงินสดที่กองไว้) ลดลงเรื่อย ๆ'),
            ('§8', 'ROIC สูงกว่า book WACC ทุกปี แต่ OCF ลดลงต่อเนื่อง'),
            ('§8', 'ไม่ได้แปลว่า ROIC ลดลงต่อเนื่อง เพราะเงินสดในตัวหารเปลี่ยน'),
            ('§9', '- ผลตอบแทนต่อผู้ถือหุ้นลดลงต่อเนื่อง'),
            ('exec', 'ROIC สูงกว่า book WACC ครบ 5 ใน 5 ปี'),
        ]:
            with self.subTest(where=where, sentence=sentence):
                self.assertEqual(self.check_text(claim(base, where, sentence)), (0, []))
        # นอกขอบเขต: §5 มีกฎของตัวเองอยู่แล้ว · §6 ไม่ใช่บทสรุป
        s6 = base.replace('\n## §6 ', '\nROIC ต่ำสุดในห้าปี\n\n## §6 ', 1)
        self.assertEqual(self.check_text(s6), (0, []))

    def test_roic_trend_gap_threshold_and_base_year(self):
        sentence = ('exec', 'ROIC FY2025 ต่ำสุดในห้าปี')
        for older, code in [(9500, 0), (4750, 0), (4655, 1)]:  # 10 · 15 (ไม่เกิน) · 15.1 จุด
            with self.subTest(older=older):
                got = self.check_text(claim(cash_years(older, 19000), *sentence))
                self.assertEqual(got[0], code, got)
                if code:
                    self.assertTrue(any('[20-tommun-roic-trend]' in f for f in got[1]), got)
        # ปีต่อปีไม่อ้างปี → ใช้ปีก่อนหน้า (FY2022 19% vs 20%) · ช่วงหลายปี/อ้าง FY2021 → ปีฐาน (1%)
        three = cash_years(950, 18050, 19000)
        self.assertEqual(self.check_text(claim(three, 'exec', 'ROIC ลดจากปีก่อนเล็กน้อย')), (0, []))
        self.assert_rule(claim(three, 'exec', 'ROIC ต่ำสุดในห้าปี'), '20-tommun-roic-trend')
        self.assert_rule(claim(three, 'exec', 'ROIC ลดจาก FY2021 มาก'), '20-tommun-roic-trend')
        # ตาราง AUDIT CASH ปีเดียว → ไม่มีคู่ให้เทียบ กฎไม่ทำงาน
        self.assertEqual(self.check_text(claim(memo(), 'exec', 'ROIC ต่ำสุดในห้าปี')), (0, []))

    def test_native_filesystem_guard(self):
        import builtins
        import io
        from unittest.mock import patch
        original_open, original_os_open, original_io_open = builtins.open, os.open, io.open
        def guard(fn):
            def checked(path,*args,**kwargs):
                if not isinstance(path,int) and '.claude' in Path(path).parts:
                    raise AssertionError('compatibility path access forbidden')
                return fn(path,*args,**kwargs)
            return checked
        for text,expected in [(memo(),0),(memo(*model(wacc={'k_e':11})),1)]:
            with tempfile.NamedTemporaryFile(mode='w',suffix='.md',dir=ROOT/'scratch',encoding='utf-8') as f:
                f.write(text); f.flush()
                with patch('builtins.open',guard(original_open)),patch('os.open',guard(original_os_open)),patch('io.open',guard(original_io_open)):
                    self.assertEqual(check_memo(f.name,PROFILE)[0],expected)
        for package in [ROOT/'tools/memocheck']:
            for path in package.rglob('*'):
                self.assertFalse(path.is_symlink(),str(path))
                if path.suffix == '.py' and not path.name.startswith('test_'):
                    self.assertNotIn('.claude',path.read_text(),str(path))

if __name__ == '__main__':
    unittest.main()
