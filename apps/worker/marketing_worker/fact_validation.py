"""Conservative numeric checks, not semantic truth certification."""
import re
import unicodedata
from decimal import Decimal

UNITS={'毫安时':('charge','1'),'mAh':('charge','1'),'Ah':('charge','1000'),'毫升':('volume','1'),'ml':('volume','1'),'mL':('volume','1'),'升':('volume','1000'),'L':('volume','1000'),'克':('mass','1'),'g':('mass','1'),'千克':('mass','1000'),'kg':('mass','1000'),'毫米':('length','1'),'mm':('length','1'),'厘米':('length','10'),'cm':('length','10'),'米':('length','1000'),'m':('length','1000'),'小时':('time','3600'),'分钟':('time','60'),'秒':('time','1'),'W':('power','1'),'瓦':('power','1'),'V':('voltage','1'),'伏':('voltage','1'),'元':('price','1'),'%':('percent','1'),'℃':('temperature','1')}
UNITS['°C']=('temperature','1')
PATTERN=re.compile(r'(?<![A-Za-z0-9.])([+-]?\d+(?:\.\d+)?)\s*('+ '|'.join(re.escape(unit) for unit in sorted(UNITS,key=len,reverse=True))+r')(?![A-Za-z])')


class NumericFactError(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__(code)


IDENTIFIER_FIELDS={'model','product_model','merchant_sku','sku','specification','型号','商品型号','商家SKU','规格'}


def quantities(text,identifiers=(),opaque_literals=()):
    text=unicodedata.normalize('NFKC',str(text))
    values=[];spans=[]
    for match in PATTERN.finditer(text):
        dimension,multiplier=UNITS[match.group(2)]
        values.append((dimension,Decimal(match.group(1))*Decimal(multiplier)))
        spans.append(match.span())
    residue=text
    for start,end in reversed(spans):residue=residue[:start]+' '* (end-start)+residue[end:]
    for literal in sorted(opaque_literals,key=len,reverse=True):
        pattern=r'(?<![A-Za-z0-9_.+*x×/-])'+re.escape(literal)+r'(?![A-Za-z0-9_.+*x×/\-\u4e00-\u9fff])'
        residue=re.sub(pattern,lambda match:' '*len(match.group()),residue)
    # Match entire identifier tokens only; never remove a numeric substring inside a claim.
    for identifier in sorted(identifiers,key=len,reverse=True):
        pattern=r'(?<![A-Za-z0-9_.-])'+re.escape(identifier)+r'(?![A-Za-z0-9_.-])'
        residue=re.sub(pattern,lambda match:' '*len(match.group()),residue)
    return values,bool(re.search(r'\d|[零一二三四五六七八九十百千万]+\s*(?:元|瓦|伏|小时|分钟|克|毫升)',residue))


def validate_numeric_claims(text,refs,facts):
    allowed=set()
    identifiers=set()
    opaque_literals=set()
    for reference in refs:
        fact=facts.get(reference)
        if not fact or fact.get('validity')!='active':raise NumericFactError('INVALID_FACT_REFERENCE')
        value=fact.get('value','')
        if isinstance(value,(dict,list)):continue
        field=fact.get('key',fact.get('id',reference))
        normalized=unicodedata.normalize('NFKC',str(value)).strip()
        if field in IDENTIFIER_FIELDS and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',normalized):
            identifiers.add(normalized)
            continue
        if field in {'specification','规格'} and re.fullmatch(r'\d+(?:\.\d+)?(?:\*\d+(?:\.\d+)?){1,2}',normalized):
            opaque_literals.add(normalized)
            continue
        values,_=quantities(str(value)+str(fact.get('unit','')))
        allowed.update(values)
    claims,unsupported=quantities(text,identifiers,opaque_literals)
    if unsupported:
        raise NumericFactError('NUMERIC_CLAIM_REVIEW_REQUIRED')
    if any(claim not in allowed for claim in claims):
        raise NumericFactError('NUMERIC_FACT_MISMATCH')


def visual_numeric_text(text):
    """Only recognized standalone frame ratios are compositional, never product quantities."""
    ratios=r'(?:9:16|16:9|1:1|3:4|4:3)'
    text=re.sub(r'^\s*'+ratios+r'\s+(?=Studio\b|studio\b|scene\b|摄影|场景)', ' ',str(text))
    return re.sub(r'(?:画幅|构图)\s*[:：]?\s*'+ratios+r'(?=\s|$|[,，。;；])',' ',text)


def repair_missing_global_refs(copy,request):
    """Attach only exact active fact values found in global copy, without changing any wording."""
    import copy as copying
    result=copying.deepcopy(copy);changes=[]
    if not isinstance(result,dict):return result,changes
    for platform,item in result.items():
        if not isinstance(item,dict) or 'fact_refs' in item:continue
        texts=[item.get(key,'') for key in ('title','body','narration','poster_title')]+item.get('selling_points',[]) if isinstance(item.get('selling_points',[]),list) else []
        texts=[unicodedata.normalize('NFKC',text) for text in texts if isinstance(text,str)]
        refs=[]
        for fact in request.get('facts',[]):
            value=fact.get('value')
            if fact.get('validity')!='active' or not isinstance(value,str) or not 1<=len(value.strip())<=200:continue
            value=unicodedata.normalize('NFKC',value).strip()
            pattern=r'(?<![A-Za-z0-9_.+*x×/-])'+re.escape(value)+r'(?![A-Za-z0-9_.+*x×/-])'
            if any(re.search(pattern,text) for text in texts):refs.append(fact['id'])
        if refs:
            item['fact_refs']=refs
            changes.append({'platform':platform,'field':'fact_refs','added_refs':refs,'rule':'exact_active_fact_value_v1'})
    return result,changes
