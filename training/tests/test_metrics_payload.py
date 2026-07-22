from django.test import SimpleTestCase

from training.views.training_view import _coerce_metrics_payload, _normalize_split_metrics


class SplitMetricsPayloadTests(SimpleTestCase):
    def test_normalizes_agent_split_aliases(self):
        result = _normalize_split_metrics({
            'splits': {
                'training': {'f1_score': 0.951, 'precision': 0.956, 'recall': 0.945, 'mAP50': 0.978, 'mAP75': 0.955},
                'val': {'f1': 0.91, 'precision': 0.92, 'recall': 0.90, 'map50': 0.94, 'map75': 0.89},
                'test': {'f1': 0.88, 'precision': 0.90, 'recall': 0.86, 'map50': 0.92, 'map75': 0.84},
            },
        })

        self.assertEqual(set(result), {'train', 'valid', 'test'})
        self.assertEqual(result['train']['f1'], 0.951)
        self.assertEqual(result['valid']['map75'], 0.89)
        self.assertEqual(result['test']['precision'], 0.90)

    def test_callback_persists_canonical_split_metrics_in_extra(self):
        result = _coerce_metrics_payload({
            'epoch': 10,
            'metrics': {
                'split_metrics': {
                    'train': {'f1': 0.95, 'precision': 0.96},
                    'valid': {'f1': 0.91, 'precision': 0.92},
                    'test': {'f1': 0.88, 'precision': 0.90},
                },
            },
        })

        self.assertEqual(result['extra']['split_metrics']['train']['f1'], 0.95)
        self.assertEqual(result['extra']['split_metrics']['valid']['precision'], 0.92)
        self.assertEqual(result['extra']['split_metrics']['test']['f1'], 0.88)

    def test_normalizes_current_gpu_metrics_and_derives_f1(self):
        result = _normalize_split_metrics({
            'best_map50': 0.9886,
            'best_map75': 0.9635,
            'precision': 0.96824,
            'recall': 0.95548,
            'train': {
                'metrics/mAP50(B)': 0.98919,
                'metrics/mAP50-95(B)': 0.87467,
                'metrics/precision(B)': 0.96355,
                'metrics/recall(B)': 0.95043,
            },
            'test': {
                'metrics/mAP50(B)': 0.96617,
                'metrics/mAP50-95(B)': 0.82575,
                'metrics/precision(B)': 0.94784,
                'metrics/recall(B)': 0.88272,
            },
        })

        self.assertAlmostEqual(result['train']['f1'], 2 * 0.96355 * 0.95043 / (0.96355 + 0.95043))
        self.assertAlmostEqual(result['test']['f1'], 2 * 0.94784 * 0.88272 / (0.94784 + 0.88272))
        self.assertAlmostEqual(result['valid']['f1'], 2 * 0.96824 * 0.95548 / (0.96824 + 0.95548))
        self.assertEqual(result['valid']['map75'], 0.9635)
        self.assertNotIn('map75', result['train'])
        self.assertNotIn('map75', result['test'])

    def test_epoch_callback_merges_validation_scores_from_extra_and_core_fields(self):
        result = _coerce_metrics_payload({
            'epoch': 10,
            'f1': 0.94045,
            'map50': 0.98503,
            'extra': {
                'precision': 0.95098,
                'recall': 0.93015,
            },
        })

        valid = result['extra']['split_metrics']['valid']
        self.assertEqual(valid['f1'], 0.94045)
        self.assertEqual(valid['map50'], 0.98503)
        self.assertEqual(valid['precision'], 0.95098)
        self.assertEqual(valid['recall'], 0.93015)
