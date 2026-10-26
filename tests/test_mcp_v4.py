"""Exercise new default negotiation and explicit historical mode over real stdio."""
import json
import os
from pathlib import Path
import tempfile
import unittest

import test_mcp_service as historical


class McpV4Tests(unittest.TestCase):
    fixture = historical.ServiceTests.fixture
    wait_job = historical.ServiceTests.wait_job

    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.inputs=self.root/'inputs'
        self.inputs.mkdir()
        config=self.root/'config.json'
        config.write_text(json.dumps(dict(allowed_input_roots=['inputs'],output_root='jobs',timeout_seconds=120)),encoding='utf-8')
        self.client=historical.Client(config)
        self.addCleanup(self.client.close)
        self.client.initialize()

    def test_real_stdio_default_and_mode_rejection(self):
        caps=self.client.tool('capabilities')['structuredContent']
        self.assertEqual((caps['protocol_id'],caps['coordinate_mode']),('fusion-step-adapted-v4.0','geometry'))
        args=self.fixture()
        for options in (dict(protocol='fusion-step-adapted-v3.0',coordinate_mode='geometry'),dict(coordinate_mode='invalid')):
            self.assertTrue(self.client.tool('evaluate',dict(args,**options))['isError'])
        self.assertEqual(self.client.tool('status')['structuredContent']['jobs'],[])

    def test_results_only_advertise_existing_html_files(self):
        from mcp_server import Service
        service=Service(self.root/'config.json')
        output=self.root/'finished'
        output.mkdir()
        service.jobs['fixture']={'job_id':'fixture','case':'box','state':'completed',
            'output_directory':str(output),'job_directory':str(self.root)}
        missing=service.results({'job_id':'fixture'})['files']
        self.assertNotIn('html',missing)
        self.assertNotIn('html_report_status',missing)
        status=output/'html-report-generation.json'
        status.write_text('{"status":"failed"}',encoding='utf-8')
        failed=service.results({'job_id':'fixture'})['files']
        self.assertNotIn('html',failed)
        self.assertEqual(failed['html_report_status'],str(status))

    @unittest.skipUnless(os.environ.get('RUN_GEOMETRY_TESTS')=='1','real v4 OCCT integration')
    def test_real_v4_box_results_retain_coordinate_and_roles(self):
        args=self.fixture(valid_step=True)
        args['coordinate_mode']='strict'
        response=self.client.tool('evaluate',args)
        self.assertFalse(response.get('isError'),response)
        job=response['structuredContent']
        self.assertEqual(job['coordinate_mode'],'strict')
        self.assertEqual(self.wait_job(job['job_id'])['state'],'completed')
        result=self.client.tool('results',{'job_id':job['job_id']})['structuredContent']
        self.assertEqual(result['summary']['coordinate_mode'],'strict')
        case=result['summary']['cases'][0]
        self.assertAlmostEqual(case['final_score'],1.,places=5)
        self.assertEqual(case['metrics']['section']['metric_role'],'diagnostic')
        self.assertIsNone(case['metrics']['section']['awarded_score'])
        self.assertTrue(Path(result['files']['html']).is_file())
        self.assertTrue(Path(result['files']['html_report_status']).is_file())


if __name__=='__main__':
    unittest.main()
