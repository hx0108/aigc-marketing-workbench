"""Prepare synthetic-only inputs and disabled provider config; never calls APIs."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    root=Path('runtime/synthetic').resolve()
    root.mkdir(parents=True,exist_ok=True)
    product=Image.new('RGB',(600,900),'white')
    draw=ImageDraw.Draw(product)
    draw.rounded_rectangle((180,180,420,720),radius=30,fill='#bd5448')
    draw.text((210,430),'SYNTHETIC',fill='white')
    mask=Image.new('L',(600,900),0)
    ImageDraw.Draw(mask).rounded_rectangle((180,180,420,720),radius=30,fill=255)
    sources={}
    for name,image in [('product',product),('mask',mask),('white_background',Image.new('RGB',(1080,1440),'white'))]:
        path=root/(name+'.png')
        if not path.exists():image.save(path)
        sources[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    config={'enabled':False,'credentials_file':str(Path.home()/'Desktop'/'AI Agent'/'.env'),'private_root':str(root),'font':'C:/Windows/Fonts/msyh.ttc','workspace':'synthetic-validation','budget_id':'synthetic-total-cny-10','total_cap':'10.0000','price_version':'minimax-cn-2026-11-11','consent_version':'synthetic-only-2026-11-11','authorized_operations':['text','product_image','dynamic','tts','video_render','poster_render'],'bounds':{'text':'0.1000','product_image':'0.0250','dynamic':'7.5000','tts':'0.0500'},'video_price_verified':True,'allowed_hosts':['cdn.hailuoai.com','algeng-video-infer.oss-cn-shanghai.aliyuncs.com','dashscope-result-bj.oss-cn-beijing.aliyuncs.com'],'sources':{'synthetic-sku':sources},'providers':{'text':{'base_url':'https://api.deepseek.com','model':'deepseek-flash'},'image':{'base_url':'https://api.minimax.cn','model':'image-01'},'video':{'base_url':'https://api.minimax.cn','model':'MiniMax-H3','parameters':{'resolution':'768P'}},'tts':{'base_url':'https://dashscope.aliyuncs.com/api/v1','model':'qwen3-tts-flash'}}}
    (root/'pipeline.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared synthetic assets and disabled configuration. No external calls.')


if __name__=='__main__':main()

