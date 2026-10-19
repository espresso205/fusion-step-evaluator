"""Exercise the actual stdio transport, job boundary and persisted evaluator output."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest

BASE = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, config):
        self.proc = subprocess.Popen([sys.executable, '-B', str(BASE/'mcp_server.py'),
            '--config', str(config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding='utf-8', cwd=BASE)
        self.responses = queue.Queue()
        self.stderr = []
        threading.Thread(target=lambda: [self.responses.put(line) for line in self.proc.stdout],
                         daemon=True).start()
        threading.Thread(target=lambda: self.stderr.extend(self.proc.stderr), daemon=True).start()
        self.counter = 0

    def raw(self, text):
        self.proc.stdin.write(text+'\n')
        self.proc.stdin.flush()
        try:
            return json.loads(self.responses.get(timeout=10))
        except queue.Empty:
            raise AssertionError('MCP response missing: '+''.join(self.stderr))

    def request(self, method, params=None):
        self.counter += 1
        result = self.raw(json.dumps({'jsonrpc':'2.0','id':self.counter,'method':method,
                                     'params':params or {}}))
        assert result['id'] == self.counter, result
        return result

    def initialize(self):
        result = self.request('initialize', {'protocolVersion':'2025-06-18',
            'capabilities':{}, 'clientInfo':{'name':'integration-test','version':'1'}})
        self.proc.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n')
        self.proc.stdin.flush()
        return result

    def tool(self, name, arguments=None):
        return self.request('tools/call', {'name':name, 'arguments':arguments or {}})['result']

    def close(self):
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
        self.proc.stdout.close()
        self.proc.stderr.close()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=BASE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root/'inputs'
        self.inputs.mkdir()
        self.output = self.root/'jobs'
        self.config = self.root/'config.json'
        self.config.write_text(json.dumps({'allowed_input_roots':['inputs'], 'output_root':'jobs',
            'timeout_seconds':120, 'max_active_jobs':1}), encoding='utf-8')
        self.client = Client(self.config)
        self.addCleanup(self.client.close)

    def fixture(self, valid_step=False, unsupported=False):
        step = self.inputs/'box.step'
        if valid_step:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
            writer = STEPControl_Writer()
            writer.Transfer(BRepPrimAPI_MakeBox(10,20,30).Shape(), STEPControl_AsIs)
            writer.Write(str(step))
        else:
            step.write_bytes(b'not a valid STEP file')
        ann = self.inputs/'annotations.json'
        item = {'id':'width','type':'plane_pair','axis':'x','nominal':10,'tol':.01}
        if unsupported:
            item['type'] = 'unsupported_probe'
        ann.write_text(json.dumps({'gt_sha256':hashlib.sha256(step.read_bytes()).hexdigest(),
            'items':[item], 'sections':[{'id':'middle','axis':'z','offset':15}]}),encoding='utf-8')
        return {'case':'box', 'candidate':str(step), 'gt':str(step), 'annotations':str(ann)}

    def wait_job(self, job_id):
        deadline = time.monotonic()+180
        while time.monotonic()<deadline:
            state = self.client.tool('status', {'job_id':job_id})['structuredContent']
            if state['state'] not in ('queued','running'):
                return state
            time.sleep(.1)
        self.fail('job did not finish within 180 seconds')

    def test_initialize_catalog_and_capabilities_without_geometry_imports(self):
        result = self.client.initialize()['result']
        self.assertEqual(result['protocolVersion'],'2025-06-18')
        self.assertIn('tools',result['capabilities'])
        tools = self.client.request('tools/list')['result']['tools']
        self.assertEqual({t['name'] for t in tools}, {'evaluate','status','results','capabilities'})
        capabilities = self.client.tool('capabilities')['structuredContent']
        self.assertEqual(capabilities['protocol_id'],'fusion-step-adapted-v3.0')
        self.assertFalse(capabilities['ranking_eligible'])
        self.assertEqual(capabilities['max_active_jobs'],1)
        self.assertEqual(self.client.request('ping')['result'],{})

    def test_protocol_errors_do_not_kill_session(self):
        self.assertEqual(self.client.request('tools/list')['error']['code'],-32002)
        self.assertEqual(self.client.raw('{')['error']['code'],-32700)
        self.assertEqual(self.client.raw('[]')['error']['code'],-32600)
        self.client.initialize()
        self.assertEqual(self.client.request('unknown')['error']['code'],-32601)
        self.assertEqual(self.client.request('tools/call',{'name':'status','arguments':[]})['error']['code'],-32602)
        self.assertTrue(self.client.tool('does_not_exist')['isError'])
        self.assertEqual(self.client.request('ping')['result'],{})

    def test_surrogate_request_ids_round_trip_without_ending_session(self):
        self.client.initialize()
        for request_id in ('\ud800', '\udfff', '中文\U0001f600'):
            with self.subTest(request_id=ascii(request_id)):
                request = {'jsonrpc':'2.0','id':request_id,'method':'ping'}
                response = self.client.raw(json.dumps(request,ensure_ascii=True))
                self.assertEqual(response['id'],request_id)
                self.assertEqual(response['result'],{})
                self.assertEqual(self.client.request('ping')['result'],{})

    def test_handshake_runs_with_site_packages_disabled(self):
        request = {'jsonrpc':'2.0','id':1,'method':'initialize',
                   'params':{'protocolVersion':'2025-06-18'}}
        run = subprocess.run([sys.executable,'-I','-S','-B',str(BASE/'mcp_server.py'),
            '--config',str(self.config)],input=json.dumps(request)+'\n',
            capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['result']['serverInfo']['name'],'fusion-step-evaluator')

    def test_invalid_configuration_fails_on_stderr_without_stdout(self):
        config = json.loads(self.config.read_text())
        config['timeout_seconds'] = 0
        self.config.write_text(json.dumps(config))
        run = subprocess.run([sys.executable,'-B',str(BASE/'mcp_server.py'),
            '--config',str(self.config)],capture_output=True,text=True,encoding='utf-8',timeout=10)
        self.assertEqual(run.returncode,2)
        self.assertEqual(run.stdout,'')
        self.assertIn('timeout_seconds',run.stderr)

    def test_paths_annotations_and_unexpected_arguments_are_rejected_without_jobs(self):
        self.client.initialize()
        args = self.fixture()
        outside = self.root/'outside.step'
        outside.write_bytes(b'private')
        cases = [dict(args,candidate=str(outside)), dict(args,candidate='../outside.step'),
                 dict(args,output=str(self.root/'escape')), dict(args,case='../escape'),
                 dict(args,candidate=str(self.inputs/'missing.step'))]
        for row in cases:
            with self.subTest(row=row):
                self.assertTrue(self.client.tool('evaluate',row)['isError'])
        ann = Path(args['annotations'])
        doc = json.loads(ann.read_text())
        doc['gt_sha256'] = '0'*64
        ann.write_text(json.dumps(doc))
        self.assertTrue(self.client.tool('evaluate',args)['isError'])
        self.assertEqual(self.client.tool('status')['structuredContent']['jobs'],[])
        self.assertTrue(self.client.tool('results',{'job_id':'../escape'})['isError'])

    def test_invalid_step_produces_failure_evidence_and_session_remains_usable(self):
        self.client.initialize()
        result = self.client.tool('evaluate', self.fixture())
        self.assertFalse(result.get('isError',False),result)
        job_id = result['structuredContent']['job_id']
        state = self.wait_job(job_id)
        self.assertEqual(state['state'],'failed')
        results = self.client.tool('results',{'job_id':job_id})['structuredContent']
        self.assertIsNone(results['summary']['batch_mean'])
        self.assertFalse(results['summary']['cases'][0]['validation_passed'])
        self.assertTrue(Path(results['files']['log']).is_file())
        self.assertEqual(self.client.request('ping')['result'],{})

    @unittest.skipUnless(os.environ.get('RUN_GEOMETRY_TESTS')=='1','set RUN_GEOMETRY_TESTS=1 for real OCCT scoring')
    def test_real_box_scores_one_with_complete_evidence_and_busy_limit(self):
        self.client.initialize()
        args = self.fixture(valid_step=True)
        before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.inputs.iterdir()}
        job_id = self.client.tool('evaluate',args)['structuredContent']['job_id']
        self.assertTrue(self.client.tool('evaluate',args)['isError'])
        self.assertTrue(self.client.tool('results',{'job_id':job_id})['isError'])
        state = self.wait_job(job_id)
        self.assertEqual(state['state'],'completed',state)
        results = self.client.tool('results',{'job_id':job_id})['structuredContent']
        summary = results['summary']
        self.assertAlmostEqual(summary['batch_mean'],1.,places=6)
        self.assertTrue(summary['code_unchanged'])
        self.assertTrue(summary['original_inputs_unchanged'])
        case = summary['cases'][0]
        self.assertEqual(case['measurement_weight_coverage'],1.)
        self.assertTrue(case['validation_passed'])
        for name in ('summary','manifest','report','comparison','aggregate','log'):
            self.assertTrue(Path(results['files'][name]).is_file(),name)
        modules = Path(results['files']['aggregate']).parent/'results'
        self.assertEqual(len(list(modules.glob('*.json'))),7)
        after = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.inputs.iterdir()}
        self.assertEqual(before,after)

    @unittest.skipUnless(os.environ.get('RUN_GEOMETRY_TESTS')=='1','set RUN_GEOMETRY_TESTS=1 for real OCCT scoring')
    def test_real_unsupported_measurement_remains_policy_lower_bound(self):
        self.client.initialize()
        job_id = self.client.tool('evaluate',self.fixture(valid_step=True,unsupported=True))['structuredContent']['job_id']
        self.assertEqual(self.wait_job(job_id)['state'],'completed')
        result = self.client.tool('results',{'job_id':job_id})['structuredContent']
        case = result['summary']['cases'][0]
        self.assertAlmostEqual(case['final_score'],.75,places=6)
        self.assertEqual(case['score_kind'],'policy_lower_bound')
        self.assertIsNone(case['metrics']['dimension']['measured_score'])
        self.assertEqual(case['metrics']['dimension']['awarded_score'],0)


if __name__ == '__main__':
    unittest.main()
