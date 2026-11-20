import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('/state/browser-evidence')
with sync_playwright() as p:
 b=p.chromium.launch(headless=False,executable_path=os.getenv('BROWSER_EXECUTABLE')); page=b.new_page()
 page.goto('https://www.vinted.lt/catalog?search_text=N100&order=newest_first',wait_until='domcontentloaded',timeout=45000); page.wait_for_timeout(2500)
 button=page.get_by_role('button',name='Palikti būtinuosius',exact=True)
 if button.count(): button.click()
 page.wait_for_timeout(1500)
 links=page.locator('a[href*="/items/"]').evaluate_all('''els=>els.map(e=>({url:e.href,title:e.getAttribute('title'),parents:[e.parentElement,e.parentElement.parentElement,e.parentElement.parentElement.parentElement,e.parentElement.parentElement.parentElement.parentElement].map(p=>({tag:p.tagName,id:p.getAttribute('data-testid'),class:p.className})),html:e.closest('[class*="new-item-box__container"]')?.outerHTML.slice(0,16000)}))''')
 (out/'inspect-cards.json').write_text(json.dumps(links,ensure_ascii=False,indent=2))
 print(json.dumps([{'url':l['url'],'title':l['title'],'parents':l['parents']} for l in links if any(s in (l['title'] or '').lower() for s in ('mini','nipogi','beelink','gmktec','n100'))],ensure_ascii=False,indent=2)[:14000])
 candidate=next((l for l in links if 'mini' in (l['title'] or '').lower()),None)
 if candidate:
  page.goto(candidate['url'],wait_until='domcontentloaded',timeout=45000); page.wait_for_timeout(2500)
  (out/'inspect-detail.txt').write_text(page.locator('body').inner_text())
  details=page.locator('[data-testid]').evaluate_all('''els=>els.filter(e=>/description|price|buy|item-title|item-status/.test(e.getAttribute('data-testid'))).map(e=>({id:e.getAttribute('data-testid'),text:e.innerText,tag:e.tagName})).slice(0,80)''')
  (out/'inspect-detail.json').write_text(json.dumps({'url':page.url,'details':details},ensure_ascii=False,indent=2))
  page.screenshot(path=str(out/'inspect-detail.png'),full_page=False)
  print(json.dumps(details,ensure_ascii=False,indent=2)[:12000])
 b.close()
