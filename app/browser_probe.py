"""Single authorized public-browser probe; stops without interacting with access challenges."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('/state/browser-evidence'); out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=False,executable_path=__import__('os').getenv('BROWSER_EXECUTABLE'))
    page=browser.new_page()
    response=page.goto('https://www.vinted.lt/catalog?search_text=N100&order=newest_first',wait_until='domcontentloaded',timeout=45000)
    page.wait_for_timeout(4000)
    body=page.locator('body').inner_text(timeout=15000)
    page.screenshot(path=str(out/'probe.png'),full_page=False)
    (out/'probe.txt').write_text(body)
    result={'status':response.status if response else None,'url':page.url,'title':page.title(),'body_excerpt':body[:5000],'links':page.locator('a[href*="/items/"]').evaluate_all('(els)=>els.slice(0,5).map(e=>({href:e.href,text:e.innerText,html:e.outerHTML.slice(0,1600),parent:e.parentElement.outerHTML.slice(0,3000)}))')}
    (out/'probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    browser.close()
