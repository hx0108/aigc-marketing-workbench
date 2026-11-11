import subprocess

import pytest
from PIL import Image

from app import local_ocr, parsing


HEADER = '\t'.join(('level','page_num','block_num','par_num','line_num','word_num','left','top','width','height','conf','text'))


def test_linux_tesseract_uses_both_languages_and_retains_word_regions(monkeypatch):
    calls = []
    monkeypatch.setattr(local_ocr,'which',lambda name:'/usr/bin/tesseract' if name=='tesseract' else None)

    def output(command, deadline):
        calls.append((command,deadline))
        if command[-1]=='--list-langs':
            return 'List of available languages (2):\neng\nchi_sim\n'
        return HEADER + '\n5\t1\t1\t1\t1\t1\t8\t12\t30\t15\t98\t重量\n5\t1\t1\t1\t1\t2\t41\t12\t22\t15\t98\t90g\n'

    monkeypatch.setattr(local_ocr,'tesseract_output',output)
    result = local_ocr.recognize_linux_pages([{'page':3,'path':'/private/page-3.png'}])[0]
    assert calls[1][0] == ['/usr/bin/tesseract','/private/page-3.png','stdout','-l','chi_sim+eng','tsv']
    assert calls[0][1] == calls[1][1]
    assert result == {'page':3,'text':'重量 90g','engine':'tesseract','confidence':None,'requires_review':True,
        'lines':[{'text':'重量 90g','words':[
            {'text':'重量','region':{'x':8,'y':12,'width':30,'height':15}},
            {'text':'90g','region':{'x':41,'y':12,'width':22,'height':15}},
        ]}]}


@pytest.mark.parametrize('binary,languages,code',[
    (None,'','LOCAL_OCR_EXECUTABLE_UNAVAILABLE'),
    ('/usr/bin/tesseract','eng\n','LOCAL_OCR_LANGUAGE_UNAVAILABLE'),
])
def test_pdf_ocr_exposes_missing_dependencies_instead_of_success(tmp_path,monkeypatch,binary,languages,code):
    path = tmp_path/'scanned.pdf'
    Image.new('RGB',(100,100),'white').save(path,'PDF')
    monkeypatch.setattr(local_ocr,'which',lambda _:binary)
    monkeypatch.setattr(local_ocr,'tesseract_output',lambda *_:languages)
    monkeypatch.setattr(parsing,'recognize_pages',local_ocr.recognize_linux_pages)
    page = parsing.parse_document(path,path.name)[0]
    assert page['status'] == 'ocr_failed'
    assert page['error_code'] == code
    assert page['requires_review'] is True and not page['text']


def test_successful_blank_output_remains_unreadable(tmp_path,monkeypatch):
    path = tmp_path/'blank.pdf'
    Image.new('RGB',(100,100),'white').save(path,'PDF')
    monkeypatch.setattr(local_ocr,'which',lambda _:'/usr/bin/tesseract')
    monkeypatch.setattr(local_ocr,'tesseract_output',lambda command,_: 'eng\nchi_sim\n' if command[-1]=='--list-langs' else HEADER)
    monkeypatch.setattr(parsing,'recognize_pages',local_ocr.recognize_linux_pages)
    page = parsing.parse_document(path,path.name)[0]
    assert page['status'] == 'unreadable' and not page['text']


def test_tesseract_uses_bounded_process_deadline(monkeypatch):
    def run(*args, **kwargs):
        assert 0 < kwargs['timeout'] <= 2
        assert kwargs['env']['OMP_THREAD_LIMIT'] == '1'
        raise subprocess.TimeoutExpired(args[0],kwargs['timeout'])

    monkeypatch.setattr(local_ocr.subprocess,'run',run)
    with pytest.raises(local_ocr.LocalOCRError,match='LOCAL_OCR_TIMEOUT'):
        local_ocr.tesseract_output(['tesseract','--list-langs'],local_ocr.monotonic()+2)
