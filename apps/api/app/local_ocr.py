"""Local OCR. All output remains unconfirmed candidate text."""
import csv
from io import StringIO
import os
from pathlib import Path
from shutil import which
from time import monotonic
import json,subprocess,sys,tempfile

class LocalOCRError(ValueError):
    """A stable error code safe to return to the document parser."""


def tesseract_output(command, deadline):
    with tempfile.TemporaryFile() as output:
        try:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise LocalOCRError('LOCAL_OCR_TIMEOUT')
            subprocess.run(command, stdout=output, stderr=subprocess.DEVNULL, timeout=remaining,
                           check=True, env={**os.environ,'OMP_THREAD_LIMIT':'1'})
            output.seek(0)
            data = output.read(2*1024*1024+1)
            if len(data) > 2*1024*1024:
                raise LocalOCRError('LOCAL_OCR_OUTPUT_TOO_LARGE')
            return data.decode('utf-8')
        except subprocess.TimeoutExpired:
            raise LocalOCRError('LOCAL_OCR_TIMEOUT') from None
        except FileNotFoundError:
            raise LocalOCRError('LOCAL_OCR_EXECUTABLE_UNAVAILABLE') from None
        except (OSError, subprocess.CalledProcessError, UnicodeError):
            raise LocalOCRError('LOCAL_OCR_FAILED') from None


def tesseract_lines(output):
    fields = ('level','page_num','block_num','par_num','line_num','word_num','left','top','width','height','conf','text')
    reader = csv.DictReader(StringIO(output), delimiter='\t', quoting=csv.QUOTE_NONE)
    if tuple(reader.fieldnames or ()) != fields:
        raise LocalOCRError('LOCAL_OCR_FAILED')
    groups = {}
    try:
        for row in reader:
            if row['level'] != '5' or not row['text'].strip():
                continue
            key = tuple(int(row[name]) for name in ('page_num','block_num','par_num','line_num'))
            region = {target:int(row[source]) for target,source in (
                ('x','left'),('y','top'),('width','width'),('height','height'),
            )}
            if min(region.values()) < 0 or not region['width'] or not region['height']:
                raise ValueError
            groups.setdefault(key,[]).append({'text':row['text'].strip(),'region':region})
    except (TypeError, ValueError, AttributeError):
        raise LocalOCRError('LOCAL_OCR_FAILED') from None

    return [{'text':' '.join(word['text'] for word in words),'words':words} for words in groups.values()]


def recognize_linux_pages(inputs):
    executable = which('tesseract')
    if not executable:
        raise LocalOCRError('LOCAL_OCR_EXECUTABLE_UNAVAILABLE')
    deadline = monotonic()+25
    languages = tesseract_output([executable,'--list-langs'],deadline)
    if not {'chi_sim','eng'} <= set(languages.splitlines()):
        raise LocalOCRError('LOCAL_OCR_LANGUAGE_UNAVAILABLE')
    results = []
    for item in inputs:
        output = tesseract_output([executable,item['path'],'stdout','-l','chi_sim+eng','tsv'],deadline)
        lines = tesseract_lines(output)
        results.append({'page':item['page'],'text':'\n'.join(line['text'] for line in lines),'lines':lines,
                        'engine':'tesseract','confidence':None,'requires_review':True})
    return results


def recognize_pages(inputs):
    if sys.platform.startswith('linux'):
        return recognize_linux_pages(inputs)
    if sys.platform!='win32':raise ValueError('LOCAL_OCR_UNAVAILABLE')
    with tempfile.TemporaryDirectory() as directory:
        manifest=Path(directory)/'inputs.json';manifest.write_text(json.dumps(inputs,ensure_ascii=False),encoding='utf-8')
        try:
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('windows_ocr.ps1')),'-Manifest',str(manifest)],capture_output=True,timeout=25,check=True)
            data=json.loads(result.stdout.decode('utf-8-sig'))
            if not isinstance(data,list):raise ValueError()
            return data
        except (subprocess.SubprocessError,ValueError,UnicodeError):raise ValueError('LOCAL_OCR_FAILED') from None
