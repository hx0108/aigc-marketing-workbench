"""Parser subprocess entry; accepts only private server paths."""
import json,sys,socket
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
# Parsers have no legitimate network operation. Prevent Python socket access.
def no_network(*args,**kwargs):raise RuntimeError('PARSER_NETWORK_DISABLED')
socket.socket=no_network
socket.create_connection=no_network
if sys.platform!='win32':
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(20,20))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from parsing import parse_document
try:
    result=parse_document(sys.argv[1],sys.argv[2])
    output=json.dumps(result,ensure_ascii=False)
    if len(output.encode('utf-8'))>5*1024*1024:raise ValueError('PARSE_OUTPUT_TOO_LARGE')
    print(output)
except Exception:
    print(json.dumps({'error':'PARSE_FAILED'}));sys.exit(1)

