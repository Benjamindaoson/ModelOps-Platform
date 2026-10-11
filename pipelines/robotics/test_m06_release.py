import json

import pytest

from pipelines.robotics.adapter import Registry, sha256_file
from pipelines.robotics.ingest_m06_release import _decision, _holm, _prob_one_sided


def test_modelops_independent_paired_gate_math():
    assert _prob_one_sided(10, 0) == 1 / 1024
    assert _holm({'standard': .01, 'corrective': .02, 'replay': .5}) == {
        'standard': .03, 'corrective': .04, 'replay': .5}
    target = {'paired_difference': .5}
    legacy = {'two_sided_95': [-.01, .01], 'one_sided_lower_95': -.02}
    validation = {'illegal_executed_actions': 0, 'valid': 1600}
    assert _decision(target, legacy, .01, 1.1, validation)[0] == 'PROMOTE'
    assert _decision(target, legacy, .1, 1.1, validation)[0] == 'INSUFFICIENT_EVIDENCE'
    assert _decision(target, legacy, .01, 1.3, validation)[0] == 'REJECT'


def test_registry_only_deploys_bound_m06_promote(tmp_path):
    weight = tmp_path / 'weight'; weight.write_bytes(b'weight')
    registry = Registry(tmp_path / 'registry')
    record = {'version': 'candidate', 'run_id': 'run', 'checkpoint': str(weight),
              'checkpoint_sha256': sha256_file(weight), 'processor_sha256': 'a'*64,
              'dataset_sha256': 'b'*64, 'base_sha256': 'c'*64}
    registry.register(record)
    references = {}
    for kind in ('protocol','validation','episodes'):
        path = tmp_path / kind
        path.write_text(json.dumps({'status':'PASS','valid':1600,'illegal_executed_actions':0,
                                               'floating_parameter_dtypes':['torch.float32'], 'tf32_allowed':False}) if kind == 'validation' else
                        json.dumps({'rules':{'backend':'fp32_eager'}}) if kind == 'protocol' else 'fixture episodes')
        references[f'{kind}_path'] = str(path)
        references[f'{kind}_sha256'] = sha256_file(path)
    evaluation = {'scope':'M06-independent','passed':True,'decision':'PROMOTE',
                  'checkpoint_sha256':sha256_file(weight),'total':400,'illegal_actions':0,
                  **references}
    registry.deploy('candidate', evaluation)
    assert json.loads((tmp_path/'registry/active.json').read_text())['version'] == 'candidate'
    with pytest.raises(ValueError):
        registry.deploy('candidate', {**evaluation,'decision':'REJECT'})
    (tmp_path/'episodes').write_text('changed')
    with pytest.raises(ValueError):
        registry.deploy('candidate', evaluation)
