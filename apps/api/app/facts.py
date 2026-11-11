"""Deterministic key/value candidates, explicitly not model-confirmed facts."""
import re

def extract_candidates(locators,source_id):
    candidates=[]
    for locator in locators:
        for line in locator.get('text','').splitlines():
            match=re.fullmatch(r'\s*([^:：=]{1,40})\s*[:：=]\s*(.{1,300})\s*',line)
            if not match:continue
            key,value=match.group(1).strip(),match.group(2).strip()
            if not key or not value:continue
            candidates.append({'key':key,'value':value,'locator':{'source_id':source_id,**{k:v for k,v in locator.items() if k in {'page','paragraph','region'}}},'origin':'rule_extraction','status':'candidate'})
    return candidates
