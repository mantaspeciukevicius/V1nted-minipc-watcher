"""Offline-testable parser for captured public classified cards only."""
from html.parser import HTMLParser
from urllib.parse import urljoin

class Cards(HTMLParser):
    def __init__(self):
        super().__init__(); self.cards=[]; self.card=None; self.stack=[]; self.depth={}; self.done=set()
    def handle_starttag(self,tag,attrs):
        a=dict(attrs); classes=set(a.get('class','').split())
        if tag=='a' and 'standard-list-item' in classes and a.get('data-item-id'):
            self.card={'url':urljoin('https://www.skelbiu.lt',a.get('href','')),'title':'','price':''};self.stack=[];self.depth={};self.done=set()
        if self.card is not None and tag not in {'img','br','input','hr','meta','link','source','wbr'}: 
            self.stack.append((tag,classes))
            for field in ('title','price'):
                if field in classes and field not in self.done and field not in self.depth: self.depth[field]=len(self.stack)
    def handle_data(self,data):
        if self.card is not None:
            for field in ('title','price'):
                if field in self.depth: self.card[field]+=data
    def handle_endtag(self,tag):
        if self.card is None: return
        if tag=='a':
            self.cards.append({k:v.strip() for k,v in self.card.items()});self.card=None;self.stack=[];return
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                self.stack=self.stack[:i]
                for field,depth in list(self.depth.items()):
                    if len(self.stack)<depth: self.done.add(field);del self.depth[field]
                break

def search_cards(html):
    parser=Cards();parser.feed(html);return parser.cards
