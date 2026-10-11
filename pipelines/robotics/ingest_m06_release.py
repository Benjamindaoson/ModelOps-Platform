"""Bind 1,600 independent MuJoCo outcomes to immutable ModelOps versions."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from pipelines.robotics.adapter import Registry, sha256_file, write

CONDITIONS = ('frozen', 'standard', 'corrective', 'replay')
SUITES = ('spatial', 'object', 'goal', 'long')

def _prob_one_sided(improved: int, worsened: int) -> float:
    n = improved + worsened
    return sum(math.comb(n, k) for k in range(improved, n + 1)) / 2**n if n else 1.0

def _holm(raw: dict[str, float]) -> dict[str, float]:
    keys = sorted(raw, key=raw.get)
    running, out = 0.0, {}
    for rank, key in enumerate(keys):
        running = max(running, min(1.0, (len(keys) - rank) * raw[key]))
        out[key] = running
    return out

def _outcome(value: str) -> bool:
    if value not in ('True', 'False'):
        raise ValueError(f'Invalid outcome: {value}')
    return value == 'True'

def _decision(target: dict, legacy: dict, adjusted_p: float, ratio: float,
              validation: dict) -> tuple[str, str]:
    if validation['illegal_executed_actions'] or validation['valid'] != 1600:
        return 'REJECT', 'safety_or_integrity_failure'
    if not math.isfinite(ratio) or ratio <= 0:
        return 'INSUFFICIENT_EVIDENCE', 'latency_unmeasured'
    if ratio > 1.2:
        return 'REJECT', 'chunk_latency_regression'
    if target['paired_difference'] < 0 or legacy['two_sided_95'][1] < -0.03:
        return 'REJECT', 'observed_target_or_supported_legacy_harm'
    if target['paired_difference'] <= 0 or adjusted_p > .05 or legacy['one_sided_lower_95'] <= -.03:
        return 'INSUFFICIENT_EVIDENCE', 'benefit_or_noninferiority_unproven'
    return 'PROMOTE', 'preregistered_simulation_gate_passed'

def ingest(evidence: Path, registry_root: Path) -> dict:
    evidence = Path(evidence)
    protocol_path = evidence / 'protocol_frozen.json'
    validation_path = evidence / 'validation.json'
    episodes_path = evidence / 'episodes.csv'
    target_path = evidence / 'target_repair.json'
    skill_path = evidence / 'skill_retention.json'
    perf_path = evidence / 'performance.json'
    decisions_path = evidence / 'release_decisions.json'
    suite_path = evidence / 'suite_metrics.json'
    manifest_path = evidence / 'manifest.json'
    for path in (protocol_path, validation_path, episodes_path, target_path, skill_path, perf_path, decisions_path, suite_path, manifest_path):
        if not path.is_file():
            raise ValueError(f'Incomplete M06 artifact: {path}')
    protocol, validation, target, skill, perf, vla_decisions, suite_metrics, manifest = [json.loads(path.read_text()) for path in
        (protocol_path, validation_path, target_path, skill_path, perf_path, decisions_path, suite_path, manifest_path)]
    if (validation.get('status') != 'PASS' or validation.get('valid') != 1600
            or manifest['protocol_sha256'] != sha256_file(protocol_path)
            or protocol['rules']['backend'] != 'fp32_eager'
            or protocol['rules']['statistics']['legacy_noninferiority_margin'] != -.03
            or protocol['rules']['release']['latency_p95_ratio_max'] != 1.2):
        raise ValueError('M06 validation/protocol gate not satisfied')
    with episodes_path.open(newline='') as stream:
        episodes = list(csv.DictReader(stream))
    expected = {(c, r['suite'], int(r['task_id']), int(r['init_state_id']))
                for c in CONDITIONS for r in protocol['cases']}
    actual = {(r['condition'], r['suite'], int(r['task_id']), int(r['init_state_id']))
              for r in episodes}
    if len(episodes) != 1600 or len(actual) != 1600 or actual != expected:
        raise ValueError('M06 matched episode coverage differs')
    rows = {(r['condition'], r['suite'], int(r['task_id']), int(r['init_state_id'])): r for r in episodes}
    for condition in CONDITIONS:
        registry_record = Registry(registry_root).resolve(manifest['modelops_registry'][condition]['version'])
        model = protocol['model_identities'][condition]
        expected_sha = model.get('adapter_sha256', model.get('model_sha256'))
        if (registry_record['checkpoint_sha256'] != expected_sha
                or sha256_file(Path(manifest['modelops_registry'][condition]['path'])) != manifest['modelops_registry'][condition]['sha256']):
            raise ValueError(f'ModelOps model identity changed: {condition}')
    raw_p = {}
    for condition in CONDITIONS[1:]:
        improved = worsened = 0
        for init in range(40, 50):
            frozen = _outcome(rows[('frozen', 'goal', 6, init)]['success'])
            candidate = _outcome(rows[(condition, 'goal', 6, init)]['success'])
            improved += int(candidate and not frozen)
            worsened += int(frozen and not candidate)
        raw_p[condition] = _prob_one_sided(improved, worsened)
        if (target[condition]['improved'] != improved or target[condition]['worsened'] != worsened
                or abs(target[condition]['one_sided_exact_p'] - raw_p[condition]) > 1e-12):
            raise ValueError(f'Target statistics do not match raw outcomes: {condition}')
    adjusted = _holm(raw_p)
    evaluations = {}
    for condition in CONDITIONS:
        registry_record = Registry(registry_root).resolve(manifest['modelops_registry'][condition]['version'])
        successes = sum(_outcome(rows[(condition, r['suite'], int(r['task_id']), int(r['init_state_id']))]['success'])
                        for r in protocol['cases'])
        if successes != suite_metrics[condition]['overall']['success']:
            raise ValueError(f'Suite summary differs from raw episodes: {condition}')
        if condition == 'frozen':
            decision, reason = 'PROMOTE', 'unchanged_incumbent_reference'
            target_stats, legacy_stats, ratio = None, None, 1.0
        else:
            target_stats = target[condition]
            legacy_stats = skill[condition]
            ratio = perf[condition]['chunk_latency_ms']['p95'] / perf['frozen']['chunk_latency_ms']['p95']
            if abs(target_stats['holm_adjusted_p'] - adjusted[condition]) > 1e-12:
                raise ValueError(f'Holm correction differs: {condition}')
            decision, reason = _decision(target_stats, legacy_stats, adjusted[condition], ratio, validation)
        if vla_decisions[condition]['decision'] != decision:
            raise ValueError(f'VLA/ModelOps release decisions differ: {condition}')
        evaluations[condition] = {'scope': 'M06-independent', 'version': registry_record['version'],
            'condition': condition, 'decision': decision, 'reason': reason,
            'passed': decision == 'PROMOTE', 'checkpoint_sha256': registry_record['checkpoint_sha256'],
            'training_run_id': registry_record['run_id'], 'dataset_sha256': registry_record['dataset_sha256'],
            'processor_sha256': registry_record['processor_sha256'],
            'total': 400, 'success': successes, 'illegal_actions': validation['illegal_executed_actions'],
            'target': target_stats, 'legacy': legacy_stats, 'chunk_latency_p95_ratio': ratio,
            'protocol_path': str(protocol_path), 'protocol_sha256': sha256_file(protocol_path),
            'validation_path': str(validation_path), 'validation_sha256': sha256_file(validation_path),
            'episodes_path': str(episodes_path), 'episodes_sha256': sha256_file(episodes_path),
            'manifest_sha256': sha256_file(manifest_path),
            'deployment_scope': 'authorized_simulation_only',
            'boundary': 'No claim of base-model pretraining disjointness or physical robot safety approval'}
    return evaluations

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = ingest(args.evidence, args.registry)
    args.output.mkdir(parents=True, exist_ok=True)
    for condition, evaluation in result.items():
        write(args.output / f'{condition}.json', evaluation)
    write(args.output / 'summary.json', {k: {'version': v['version'], 'decision': v['decision'],
          'reason': v['reason'], 'success': v['success'], 'total': v['total']} for k,v in result.items()})
    print(json.dumps({k: v['decision'] for k,v in result.items()}, sort_keys=True))

if __name__ == '__main__':
    main()
