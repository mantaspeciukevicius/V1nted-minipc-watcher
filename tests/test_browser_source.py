import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from browser_source import access_problem, availability, price_from_text, source_config, collect

class BrowserTests(unittest.TestCase):
    def test_eur(self): self.assertEqual(price_from_text('95,00 €'),('95.00','EUR'))
    def test_prefix_eur(self): self.assertEqual(price_from_text('€ 95.50'),('95.50','EUR'))
    def test_pln(self): self.assertEqual(price_from_text('400,00 zł'),('400.00','PLN'))
    def test_czk(self): self.assertEqual(price_from_text('2 100,00 Kč'),('2100.00','CZK'))
    def test_two_totals_unknown(self): self.assertEqual(price_from_text('100 €\n105.70 € buyer fee included'),(None,None))
    def test_no_currency_unknown(self): self.assertEqual(price_from_text('100'),(None,None))
    def test_403(self): self.assertEqual(access_problem(403,'','https://www.vinted.lt/catalog'),'ACCESS_BLOCKED')
    def test_429(self): self.assertEqual(access_problem(429,'','https://www.vinted.lt/catalog'),'RATE_LIMIT')
    def test_challenge(self): self.assertEqual(access_problem(200,'Verify you are human','https://www.vinted.lt'),'ACCESS_BLOCKED')
    def test_login(self): self.assertEqual(access_problem(200,'Sign in','https://www.vinted.lt/login'),'LOGIN_REQUIRED')
    def test_normal(self): self.assertIsNone(access_problem(200,'Mini PC N100','https://www.vinted.lt/catalog'))
    def test_no_purchase_not_available(self): self.assertEqual(availability('Mini PC N100'), 'UNKNOWN')
    def test_buy_button(self): self.assertEqual(availability('Mini PC',True),'AVAILABLE_CONFIRMED')
    def test_sold_overrides_button(self): self.assertEqual(availability('Parduota\nMini PC',True),'SOLD')
    def test_reserved(self): self.assertEqual(availability('Réservé\nMini PC'),'RESERVED')
    def test_unsupported_market(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'; p.write_text(json.dumps({'markets':['evil.com']}))
            with self.assertRaises(ValueError): source_config(p)
    def test_detail_limit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'; p.write_text(json.dumps({'max_details':999}))
            with self.assertRaises(ValueError): source_config(p)
    def test_missing_auth(self):
        with tempfile.TemporaryDirectory() as d:
            records,statuses=collect(Path(d),None,None,Path(d)/'config')
            self.assertEqual(records,[]); self.assertEqual(statuses[0]['state'],'UNAVAILABLE')

    def test_challenge_latch_no_browser_request(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); config=root/'config'; config.mkdir()
            (config/'direct-authorization.json').write_text('{}')
            (root/'browser-access-paused.json').write_text('{}')
            records,statuses=collect(root,None,None,config)
            self.assertEqual(records,[]); self.assertEqual(statuses[0]['state'],'ACCESS_BLOCKED')
    def test_exclude_phone(self):
        from browser_source import candidate_hint
        self.assertFalse(candidate_hint('OnePlus Nord N100 16GB'))
    def test_exclude_helmet(self):
        from browser_source import candidate_hint
        self.assertFalse(candidate_hint('Kask Nolan N100-5'))
    def test_exclude_laptop(self):
        from browser_source import candidate_hint
        self.assertFalse(candidate_hint('Laptop Chuwi N100 16GB RAM'))
    def test_mini_candidate(self):
        from browser_source import candidate_hint
        self.assertTrue(candidate_hint('Mini PC NiPoGi N100 16GB'))
    def test_unknown_model_candidate(self):
        from browser_source import candidate_hint
        self.assertTrue(candidate_hint('Beelink S12 Pro'))
    def test_description_boundaries(self):
        from browser_source import listing_section
        text='Menu\nMini PC\nN100 16GB\nSiuntimas\nRelated N150 8GB'
        self.assertEqual(listing_section(text,'Mini PC').strip(),'N100 16GB')
    def test_exclude_nokia_storage(self):
        from browser_source import candidate_hint
        self.assertFalse(candidate_hint('Nokia N97 32GB'))
    def test_404_not_access_challenge(self): self.assertEqual(access_problem(404,'','https://vinted.lv/catalog'),'SOURCE_UNAVAILABLE')
    def test_legacy_netbook_model_is_not_cpu(self):
        from browser_source import candidate_hint
        self.assertFalse(candidate_hint('Ordinateur Samsung N150 Plus'))
    def test_pc_portable_is_laptop(self):
        from browser_source import candidate_hint
        self.assertFalse(candidate_hint('PC portable Lenovo 3000 N100'))
