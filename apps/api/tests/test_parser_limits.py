import unittest,subprocess,sys
from app.parser_limits import ProcessLimits
class ParserLimitTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='win32','Windows Job Object test')
    def test_large_allocation_is_denied_by_process_memory_limit(self):
        code="input()\ntry:\n x=bytearray(256*1024*1024)\n print('unlimited')\nexcept MemoryError:\n print('limited')"
        process=subprocess.Popen([sys.executable,'-I','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        limits=None
        try:
            limits=ProcessLimits(process,memory_bytes=64*1024*1024,cpu_seconds=5)
            output,error=process.communicate('\n',timeout=10)
            self.assertEqual(output.strip(),'limited')
        finally:
            if process.poll() is None:process.kill();process.wait()
            if limits:limits.close()
    @unittest.skipUnless(sys.platform=='win32','Windows Job Object test')
    def test_cpu_limit_terminates_busy_parser(self):
        process=subprocess.Popen([sys.executable,'-I','-c','input()\nwhile True: pass'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        limits=None
        try:
            limits=ProcessLimits(process,cpu_seconds=1)
            process.communicate('\n',timeout=8)
            self.assertNotEqual(process.returncode,0)
        finally:
            if process.poll() is None:process.kill();process.wait()
            if limits:limits.close()
