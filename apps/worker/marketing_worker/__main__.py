import signal
import threading
import uuid
import os
from app.job_repository import JobRepository
from app.sources import ROOT
from .runner import run_with_heartbeat
from .business import configured_services

stop = threading.Event()
if os.environ.get('AIGC_PIPELINE_CONFIG'):
    from .configuration import load_configuration
    load_configuration(os.environ['AIGC_PIPELINE_CONFIG'])
signal.signal(signal.SIGINT, lambda *_: stop.set())
signal.signal(signal.SIGTERM, lambda *_: stop.set())
run_with_heartbeat(JobRepository(), str(uuid.uuid4()), stop, ROOT, configured_services)
