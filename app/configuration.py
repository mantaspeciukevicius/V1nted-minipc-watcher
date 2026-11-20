"""Conservative seller-configuration evidence in Lithuanian, Polish and English."""
import re

def evidence(text):
    t=text.lower();flags=[]
    patterns={
      'RAM_NOT_INSTALLED':r'without\s+ram|no\s+ram|be\s+(?:ram|(?:operatyviosios\s+)?atminties)|bez\s+(?:pamięci\s+)?ram|ram\s+(?:nepridedama|nėra|brak)|brak\s+(?:pamięci\s+)?ram',
      'OPTIONAL_CONFIGURATION':r'barebones?|(?:optional|papildomai|atskirai|opcjonaln\w*|za dopłatą|už papildomą).{0,35}(?:ram|gb|ssd)|(?:ram|\d+\s*gb).{0,20}(?:optional|papildomai|atskirai|za dopłatą)|(?:galima|możliwość).{0,20}(?:pridėti|dokupienia|dokupić)',
      'STORAGE_MISSING':r'without\s+(?:ssd|storage|disk)|no\s+ssd|be\s+(?:ssd|disko|diskų)|bez\s+(?:dysku|ssd)|brak\s+dysku',
      'POWER_ADAPTER_MISSING':r'without\s+(?:power\s+)?adapter|no\s+(?:power\s+)?adapter|be\s+(?:maitinimo|adapterio)|bez\s+zasilacza|brak\s+zasilacza',
      'DEFECTIVE':r'\b(?:broken|defective|neveikia|sugedęs|uszkodzony|niesprawny)\b',
    }
    for flag,pattern in patterns.items():
        if re.search(pattern,t,re.S): flags.append(flag)
    # Shipping/collection charges are not a second computer configuration.
    offer_lines=[line for line in t.splitlines() if not re.search(r'siuntim|pristatym|wysyłk|dostaw|shipping|delivery',line)]
    amounts=set(re.findall(r'\b\d+(?:[.,]\d+)?\s*(?:€|eur)', '\n'.join(offer_lines)))
    if len(amounts)>1: flags.append('MULTIPLE_CONFIGURATION_PRICES')
    return flags

def memory_text(text):
    # Strip explicit supported/upgrade capacities before installed RAM extraction.
    unit=r'(?:gb|go|гб|gib|mb)'
    labels=r'(?:supports?(?:\s+up\s+to)?|up\s+to|max(?:imum)?(?:\s+supported)?(?:\s+(?:ram|memory))?|palaiko(?:\s+iki)?|maksimaliai|maksimali(?:\s+atmintis)?|maksymalnie|maksymalna(?:\s+pamięć)?|obsługuje(?:\s+do)?|rozbudowa\s+do|galima\s+(?:padidinti|išplėsti)\s+iki)'
    return re.sub(labels+r'\s*[:=]?\s*\d+\s*'+unit,'',text,flags=re.I)
