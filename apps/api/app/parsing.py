"""Local bounded document parsing, retaining exact paragraph/page locators."""
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
try:from .local_ocr import LocalOCRError, recognize_pages
except ImportError:from local_ocr import LocalOCRError, recognize_pages

def parse_document(path,name):
    if name.lower().endswith('.txt'):
        return [{'paragraph':i+1,'text':line} for i,line in enumerate(Path(path).read_text(encoding='utf-8').splitlines()) if line.strip()]
    if name.lower().endswith('.pdf'):
        from pypdf import PdfReader
        reader=PdfReader(path)
        if reader.is_encrypted or len(reader.pages)>100:raise ValueError('PDF_INVALID')
        result=[]
        for i,page in enumerate(reader.pages):
            text=page.extract_text() or ''
            result.append({'page':i+1,'text':text,'status':'parsed' if text.strip() else 'ocr_required'})
        scanned=[entry for entry in result if entry['status']=='ocr_required']
        if scanned:
            import tempfile
            try:
                import pypdfium2 as pdfium
                with tempfile.TemporaryDirectory() as directory:
                    document=pdfium.PdfDocument(str(path));inputs=[]
                    try:
                        for entry in scanned:
                            page=document[entry['page']-1]
                            try:
                                width,height=page.get_size()
                                bitmap=page.render(scale=min(2,2000/max(width,height)))
                                try:
                                    image_path=Path(directory)/(str(entry['page'])+'.png')
                                    image=bitmap.to_pil();image.save(image_path)
                                    entry['rendered_size']=[image.width,image.height]
                                    entry['page_size_points']=[width,height]
                                finally:bitmap.close()
                                inputs.append({'page':entry['page'],'path':str(image_path)})
                            finally:page.close()
                    finally:document.close()
                    recognized={item['page']:item for item in recognize_pages(inputs)}
                    for entry in scanned:
                        candidate=recognized.get(entry['page'],{})
                        text='\n'.join(line['text'] for line in candidate.get('lines',[]))
                        entry.update({**candidate,'text':text,'status':'ocr_candidate' if text.strip() else 'unreadable','requires_review':True,'confidence':None,'coordinate_space':'rendered_page_pixels'})
            except LocalOCRError as error:
                for entry in scanned:entry.update({'status':'ocr_failed','error_code':str(error),'requires_review':True})
            except (ImportError,ValueError,OSError):
                for entry in scanned:entry.update({'status':'ocr_failed','error_code':'LOCAL_OCR_UNAVAILABLE_OR_FAILED','requires_review':True})
        return result
    if name.lower().endswith('.docx'):
        with ZipFile(path) as archive:
            info=archive.getinfo('word/document.xml')
            if info.file_size>10*1024*1024:raise ValueError('DOCUMENT_TOO_LARGE')
            data=archive.read(info)
            if b'<!DOCTYPE' in data or b'<!ENTITY' in data:raise ValueError('XML_UNSAFE')
            root=ET.fromstring(data)
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        return [{'paragraph':i+1,'text':''.join(p.itertext())} for i,p in enumerate(root.findall('.//w:p',ns))]
    raise ValueError('OCR_REQUIRED')


def parse_isolated(path,name):
    import subprocess,sys,json,tempfile
    from .parser_limits import ProcessLimits
    with tempfile.TemporaryFile() as output:
        process=subprocess.Popen([sys.executable,'-I',str(Path(__file__).with_name('parser_process.py')),str(path),name],stdout=output,stderr=subprocess.DEVNULL)
        limits=None
        try:
            limits=ProcessLimits(process,active_processes=2)
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill();process.wait();raise ValueError('PARSE_TIMEOUT') from None
        except OSError:
            process.kill();process.wait();raise ValueError('PARSER_LIMIT_UNAVAILABLE') from None
        finally:
            if limits:limits.close()
        output.seek(0);data=output.read(5*1024*1024+1)
        if process.returncode or len(data)>5*1024*1024:raise ValueError('PARSE_FAILED')
        return json.loads(data)
