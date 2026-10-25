"""Versioned MCP and offline-analysis boundaries, without geometry imports."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import mcp_server
from analysis.ablation import analyze_dataset
from analysis.system_comparison import compare_systems
from analysis.result_reader import read_source
from test_result_reader import v3_fixture, write_json
import hashlib
import test_contract_v4 as contract_tests


V4 = 'fusion-step-adapted-v4.0'
V3 = 'fusion-step-adapted-v3.0'
WEIGHTS = dict(shape=6/13, dimension=5/13, distance=0., mass=2/13, face_match=0., section=0.)


def dataset(mode='geometry', label='A'):
    measured = dict(shape=.8, dimension=.6, distance=None, mass=1., face_match=None, section=None)
    awards = dict(measured)
    row = dict(case='part', measured_scores=measured, awarded_scores=awards,
               baseline_score=9.8/13, original_weight_coverage=1., participates=True,
               score_kind='measured', status='ok', execution={}, metric_statuses={},
               input_hashes=dict(gt='a'*64, annotations='b'*64))
    return dict(source_id=label, system=label, source_protocol_id=V4, coordinate_mode=mode,
                weights=WEIGHTS, records=[row], warnings=[])


def v4_fixture(root):
    v3_fixture(root)
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    manifest = read(root/'manifest.json')
    manifest.update(schema_version='4.0', protocol_id=V4, coordinate_mode='geometry',
                    weights=dict(protocol_id=V4, weights=WEIGHTS))
    write_json(root/'manifest.json', manifest)
    digest = hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()
    assessment = read(root/'Q01/aggregate.json')
    assessment.update(schema_version='4.0', protocol_id=V4, coordinate_mode='geometry',
                      run_manifest_sha256=digest, weights=WEIGHTS, unavailable_metrics=[],
                      diagnostic_unavailable_metrics=['distance','face_match','section'])
    pose = dict(schema_version='4.0', protocol_id=V4, coordinate_mode='geometry', case='Q01', angle='pose',
                run_manifest_sha256=digest, input_hashes=dict(candidate='a'*64,gt='b'*64,annotations='c'*64),
                status='ok', score=1., quality=dict(measurement_valid=True),
                raw=dict(evaluation_candidate_sha256='e'*64, aligned_candidate_sha256='e'*64))
    assessment['pose'] = pose
    write_json(root/'Q01/results/pose.json', pose)
    for name, metric in assessment['metrics'].items():
        role = 'scored' if name in ('shape','dimension','mass') else 'validation' if name=='validity' else 'diagnostic'
        metric.update(metric_role=role, coordinate_mode='geometry')
        metric['evidence']['run_manifest_sha256'] = digest
        path = root/'Q01/results'/f'{name}.json'
        module = read(path)
        module.update(schema_version='4.0', protocol_id=V4, coordinate_mode='geometry', run_manifest_sha256=digest)
        evaluation_hashes = dict(module['input_hashes'])
        if name in ('shape','dimension','distance','face_match','section'):
            evaluation_hashes['candidate']='e'*64
        module['evaluation_input_hashes']=evaluation_hashes
        metric['evidence']['evaluation_input_hashes']=evaluation_hashes
        if role=='validation':
            metric['awarded_score']=None
        if role=='diagnostic':
            module.update(status='evaluator_error', score=None, quality=dict(measurement_valid=False))
            metric.update(status='evaluator_error', value=None, score=None, measured_score=None,
                          awarded_score=None, score_source='diagnostic_unavailable')
            assessment['module_scores'][name]=None
            assessment['awarded_module_scores'][name]=None
        write_json(path, module)
    profile=assessment['scores'].pop(V3)
    assessment['scores'][V4]=profile
    write_json(root/'Q01/aggregate.json',assessment)
    summary=read(root/'summary.json')
    summary.update(schema_version='4.0',protocol_id=V4,coordinate_mode='geometry',run_manifest_sha256=digest,cases=[assessment])
    write_json(root/'summary.json',summary)
    return summary


def v4_contract_fixture(root, rows):
    from src.contract_v4 import aggregate_case
    manifest=dict(schema_version='4.0',protocol_id=V4,coordinate_mode='geometry',
                  weights=dict(protocol_id=V4,weights=WEIGHTS),cases=[dict(case='case1',expected_hashes=contract_tests.HASHES)])
    write_json(root/'manifest.json',manifest)
    digest=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()
    for name,row in rows.items():
        row['run_manifest_sha256']=digest
        write_json(root/'case1/results'/f'{name}.json',row)
    assessment=aggregate_case('case1',rows,contract_tests.HASHES)
    assessment.update(run_manifest_sha256=digest,execution=dict(status='completed',timed_out=False,returncode=0))
    write_json(root/'case1/aggregate.json',assessment)
    write_json(root/'summary.json',dict(schema_version='4.0',protocol_id=V4,coordinate_mode='geometry',run_manifest_sha256=digest,
        cases=[assessment],code_unchanged=True,original_inputs_unchanged=True,
        total_case_count=1,participating_case_count=int(assessment['participates_in_scoring']),batch_mean=assessment['final_score']))


class InterfacesV4Tests(unittest.TestCase):
    def service(self, **options):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root/'inputs').mkdir()
        config = dict(allowed_input_roots=['inputs'], output_root='outputs', **options)
        path = root/'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        return mcp_server.Service(path)

    def test_default_mcp_declares_v4_geometry_and_explicit_metric_roles(self):
        result = self.service().capabilities()
        self.assertEqual(result['protocol_id'], V4)
        self.assertEqual(result['coordinate_mode'], 'geometry')
        self.assertEqual(set(result['scored_metrics']), {'shape', 'dimension', 'mass'})
        self.assertEqual(set(result['diagnostic_metrics']), {'distance', 'face_match', 'section'})
        self.assertEqual(result['weights'], WEIGHTS)

    def test_mcp_rejects_implicit_alignment_for_v3(self):
        with self.assertRaisesRegex(ValueError, 'coordinate'):
            self.service(protocol=V3, coordinate_mode='geometry')
        result = self.service(protocol=V3).capabilities()
        self.assertEqual(result['coordinate_mode'], 'strict')
        self.assertEqual(result['protocol_id'], V3)

    def test_mcp_tool_catalog_exposes_only_valid_protocol_and_coordinate_options(self):
        schema = next(t for t in mcp_server.TOOLS if t['name']=='evaluate')['inputSchema']['properties']
        self.assertEqual(set(schema['protocol']['enum']), {V3,V4})
        self.assertEqual(set(schema['coordinate_mode']['enum']), {'geometry','strict'})

    def test_v4_core_complete_does_not_require_diagnostics_and_has_seven_variants(self):
        original = dataset()
        before = copy.deepcopy(original)
        result = analyze_dataset(original)
        self.assertEqual(result['counts']['complete'], 1)
        self.assertEqual(result['coordinate_mode'], 'geometry')
        variants = result['cohorts']['complete_measurements']['variants']
        self.assertEqual(len(variants), 7)
        self.assertEqual({v['removed_metric'] for v in variants}, {None,'shape','dimension','mass'})
        removed = next(v for v in variants if v['id']=='without_mass_renormalized')
        self.assertAlmostEqual(removed['ranking'][0]['score'], 7.8/11)
        self.assertEqual(before, original)

    def test_v4_different_coordinate_modes_cannot_enter_system_comparison(self):
        left, right = dataset(), dataset('strict','B')
        result = compare_systems([left,right], [analyze_dataset(left),analyze_dataset(right)])
        self.assertEqual(result['status'], 'not_applicable')
        self.assertIn('different_coordinate_modes', result['reasons'])

    def test_v4_analysis_rejects_diagnostic_weight_and_absent_coordinate_mode(self):
        data=dataset()
        data['weights']=dict(WEIGHTS,distance=.1,shape=WEIGHTS['shape']-.1)
        with self.assertRaisesRegex(ValueError,'v4'):
            analyze_dataset(data)
        data=dataset()
        del data['coordinate_mode']
        with self.assertRaisesRegex(ValueError,'coordinate'):
            analyze_dataset(data)

    def test_v4_reader_accepts_diagnostic_failure_without_downgrading_core(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            v4_fixture(root)
            result=read_source(root)
            self.assertEqual(result['coordinate_mode'],'geometry')
            self.assertEqual(result['records'][0]['score_kind'],'measured')
            self.assertEqual(result['records'][0]['original_weight_coverage'],1.)
            self.assertEqual(analyze_dataset(result)['counts']['complete'],1)

    def test_v4_reader_rejects_mode_and_derived_hash_tampering(self):
        for field,value in (('coordinate_mode','strict'),('evaluation_input_hashes',dict(candidate='f'*64,gt='b'*64,annotations='c'*64))):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                root=Path(d)
                v4_fixture(root)
                path=root/'Q01/results/shape.json'
                module=json.loads(path.read_text(encoding='utf-8'))
                module[field]=value
                write_json(path,module)
                with self.assertRaisesRegex(ValueError,'coordinate|evaluation'):
                    read_source(root)

    def test_real_v4_contract_missing_core_invalid_and_inconclusive_are_preserved(self):
        for variant in ('missing_core','invalid','inconclusive','pose_failure'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as d:
                rows=contract_tests.records()
                if variant=='missing_core': rows.pop('dimension')
                elif variant=='invalid':
                    rows={'validity':rows['validity']}
                    rows['validity'].update(status='candidate_invalid',score=0.)
                    rows['validity']['quality']['candidate_invalid_confirmed']=True
                elif variant=='inconclusive': rows={}
                else:
                    rows={k:v for k,v in rows.items() if k in ('validity','mass','pose')}
                    rows['pose'].update(status='evaluator_error',score=None,quality=dict(measurement_valid=False),raw={})
                root=Path(d)
                v4_contract_fixture(root,rows)
                result=read_source(root)
                record=result['records'][0]
                self.assertEqual(record['participates'],variant in ('missing_core','pose_failure'))
                if variant=='missing_core': self.assertAlmostEqual(record['baseline_score'],8/13)
                if variant=='pose_failure': self.assertAlmostEqual(record['baseline_score'],2/13)


if __name__ == '__main__':
    unittest.main()
