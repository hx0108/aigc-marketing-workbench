"""Versioned creative specifications are inert data, never executable agent skills."""
import re
VERSION='creative-direction-v1'
CATEGORIES={
 'general':{'props':['none','paper_card'],'scenes':['studio','tabletop'],'rule':'Unknown or ambiguous category: neutral presentation only.'},
 'headphones':{'props':['none','notebook'],'scenes':['studio','tabletop','desk'],'rule':'Only explicit confirmed category/name headphone terms; no hearing, ANC or battery claims.'},
 'hair_dryer':{'props':['none','folded_towel'],'scenes':['studio','tabletop','vanity'],'rule':'Only explicit confirmed category/name hair-dryer terms; no hair-effect, heat or power claims.'},
}
OPTIONS={
 'palette':{'warm_neutral':'warm ivory and muted beige','cool_neutral':'cool grey and pale blue','red_complement':'muted red accents against ivory','blue_complement':'muted blue accents against cream','high_contrast':'dark charcoal with clear ivory accents'},
 'surface':{'matte':'matte display surface','paper':'subtle paper texture on the background','wood':'light wood background surface','stone':'subtle stone background surface'},
 'scene':{'studio':'abstract studio display','tabletop':'editorial tabletop','desk':'uncluttered desk setting','vanity':'uncluttered vanity setting'},
 'lighting':{'side':'controlled directional side light','rim':'restrained rim light around display space','window':'soft diffused window light','overcast':'even overcast daylight'},
 'composition':{'center':'central focal area with clean margins','diagonal':'subtle diagonal background lines around central clear space','negative_space':'central clear product space and generous breathing room'},
 'props':{'none':'no props','paper_card':'one plain unbranded paper card away from product space','notebook':'one closed unbranded notebook at frame edge','folded_towel':'one folded plain towel at frame edge'},
 'camera':{'push_in':'camera pushes in gently, holds the product detail, then settles','lateral_reveal':'camera moves sideways slightly to reveal the existing product, then holds','slow_drift':'camera drifts slowly across the scene, ending on a steady product view','stable_closeup':'begin wide, move slowly toward a close-up, then hold steady'},
 'information_order':{'hero_detail_close':'establish the hero product, inspect existing visible details, finish with a clean hold','context_detail_choice':'establish the styled setting, inspect visible detail, leave clean space for verified selection information'},
 'rhythm':{'hook_hold':'short visual opening followed by a longer detail hold','observe_hold':'calm establishing view followed by an unhurried detail hold'},
}
PLATFORM={
 'douyin':{'lighting':['side','rim'],'camera':['push_in','lateral_reveal'],'rhythm':['hook_hold'],'information_order':['hero_detail_close'],'composition':['center','diagonal']},
 'xiaohongshu':{'lighting':['window','overcast'],'camera':['slow_drift','stable_closeup'],'rhythm':['observe_hold'],'information_order':['context_detail_choice'],'composition':['negative_space','center']},
}
FIDELITY=' Preserve the supplied product pixels, silhouette, proportions, logo, buttons, color and material. Do not deform, recolor, rotate to invent hidden surfaces, add parts, people, text, claims or logos. Keep the product stationary; move only the camera subtly. No unsupported functionality or demonstrations.'

def category_for(facts):
    values=[str(f.get('value','')).strip().casefold() for f in facts if f.get('validity')=='active' and f.get('id') in {'category','product_category','name','product_name'}]
    matched=set()
    for value in values:
        # Conservative short noun values; instruction-like long source text never classifies.
        if len(value)>60 or re.search(r'https?://|ignore|instruction|忽略|指令|执行',value):continue
        if any(term in value for term in ('耳机','headphone','earbud')):matched.add('headphones')
        if any(term in value for term in ('吹风机','hair dryer','hairdryer')):matched.add('hair_dryer')
    return next(iter(matched)) if len(matched)==1 else 'general'

def specification(facts,platform):
    category=category_for(facts)
    choices={key:list(values) for key,values in OPTIONS.items()}
    choices.update(PLATFORM[platform]);choices['scene']=CATEGORIES[category]['scenes'];choices['props']=CATEGORIES[category]['props']
    return {'version':VERSION,'category':category,'choices':choices,'boundary':'Visual choices describe set styling, never product material, function or unconfirmed appearance. Emit only enum tokens.'}

def fallback_plan(facts,platform):
    spec=specification(facts,platform)
    plan={key:values[0] for key,values in spec['choices'].items()}
    plan.update(version=VERSION,category=spec['category'])
    # Only a closed color mapping affects the set, never interpolate source text into prompts.
    values=' '.join(str(f.get('value','')) for f in facts if f.get('validity')=='active')
    if '红色' in values:plan['palette']='red_complement'
    elif '蓝色' in values:plan['palette']='blue_complement'
    elif platform=='douyin':plan['palette']='high_contrast'
    if platform=='xiaohongshu':plan['scene']='tabletop'
    return plan

def validate_plan(plan,facts,platform):
    spec=specification(facts,platform)
    if not isinstance(plan,dict) or set(plan)!=set(OPTIONS)|{'version','category'}:raise ValueError('invalid_visual_plan_fields')
    if plan['version']!=VERSION or plan['category']!=spec['category']:raise ValueError('visual_plan_scope_mismatch')
    for key,values in spec['choices'].items():
        if not isinstance(plan[key],str) or plan[key] not in values:raise ValueError('invalid_visual_plan_'+key)
    return plan

def resolved_plan(item,facts,platform):
    return validate_plan(item.get('visual_plan',fallback_plan(facts,platform)),facts,platform)

def image_prompt(plan):
    text='Empty product photography background only. No product, text, logos or people. Leave the central product area completely clear. '+'. '.join(OPTIONS[key][plan[key]] for key in ('palette','surface','scene','lighting','composition','props'))+'. Background materials never describe or change the product.'
    if len(text)>1500:raise ValueError('image_prompt_too_long')
    return text

def video_prompt(plan):
    text='Create a product presentation shot. Set direction: '+'. '.join(OPTIONS[key][plan[key]] for key in ('palette','scene','lighting','composition','camera','rhythm','information_order'))+'.'+FIDELITY
    if len(text)>2000:raise ValueError('video_prompt_too_long')
    return text
