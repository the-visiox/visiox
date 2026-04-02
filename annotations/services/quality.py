"""
Annotation quality scoring:
  - IoU (Intersection over Union) for bounding-box pairs
  - Cohen's κ (kappa) for class-label agreement between annotators
  - Inter-annotator agreement summary for a media item or dataset
"""
from collections import defaultdict

from annotations.models import Annotation


# ── Geometry helpers ─────────────────────────────────────────────────────────

def bbox_iou(a: dict, b: dict) -> float:
    """Compute IoU between two bbox dicts {x, y, w, h}."""
    ax1, ay1 = a.get('x', 0), a.get('y', 0)
    ax2, ay2 = ax1 + a.get('w', 0), ay1 + a.get('h', 0)
    bx1, by1 = b.get('x', 0), b.get('y', 0)
    bx2, by2 = bx1 + b.get('w', 0), by1 + b.get('h', 0)

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
    a_area = (ax2 - ax1) * (ay2 - ay1)
    b_area = (bx2 - bx1) * (by2 - by1)
    union_area = a_area + b_area - inter_area

    return inter_area / union_area if union_area > 0 else 0.0


# ── Cohen's κ ────────────────────────────────────────────────────────────────

def cohens_kappa(labels_a: list, labels_b: list) -> float:
    """
    Compute Cohen's κ given two lists of labels of equal length.
    Returns float in [-1, 1]; 1 = perfect agreement.
    """
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0

    n = len(labels_a)
    categories = set(labels_a) | set(labels_b)

    # Observed agreement
    p_o = sum(a == b for a, b in zip(labels_a, labels_b)) / n

    # Expected agreement
    p_e = sum(
        (labels_a.count(c) / n) * (labels_b.count(c) / n)
        for c in categories
    )

    return (p_o - p_e) / (1 - p_e) if p_e < 1 else 1.0


# ── Inter-annotator agreement for a media item ───────────────────────────────

def media_agreement(media_id: int) -> dict:
    """
    Compute per-class IoU agreement and Cohen's κ for all annotators
    who labelled the given media item.
    """
    annotations = list(
        Annotation.objects.filter(media_id=media_id)
        .select_related('annotator', 'class_label')
    )

    annotators = list({a.annotator_id for a in annotations if a.annotator_id})

    if len(annotators) < 2:
        return {
            'media_id': media_id,
            'annotator_count': len(annotators),
            'message': 'At least 2 annotators required for agreement scoring.',
            'iou_matrix': [],
            'cohens_kappa': None,
        }

    # Group bbox annotations by annotator
    by_annotator: dict[int, list[Annotation]] = defaultdict(list)
    for ann in annotations:
        if ann.annotator_id:
            by_annotator[ann.annotator_id].append(ann)

    # Build label vectors for kappa (by class_label name for simplicity)
    # Use the intersection of bbox annotations matched greedily by IoU
    iou_results = []
    kappa_labels_a, kappa_labels_b = [], []

    ann_a = [a for a in by_annotator.get(annotators[0], []) if a.type == 'bbox']
    ann_b = [a for a in by_annotator.get(annotators[1], []) if a.type == 'bbox']

    used_b = set()
    for a in ann_a:
        best_iou, best_b = 0.0, None
        for idx, b in enumerate(ann_b):
            if idx in used_b:
                continue
            iou = bbox_iou(a.data or {}, b.data or {})
            if iou > best_iou:
                best_iou, best_b = iou, idx

        if best_b is not None:
            used_b.add(best_b)
            matched = ann_b[best_b]
            iou_results.append({
                'annotation_a': a.id,
                'annotation_b': matched.id,
                'iou': round(best_iou, 4),
            })
            kappa_labels_a.append(a.class_label.name)
            kappa_labels_b.append(matched.class_label.name)

    kappa = cohens_kappa(kappa_labels_a, kappa_labels_b) if kappa_labels_a else None

    return {
        'media_id': media_id,
        'annotator_count': len(annotators),
        'matched_pairs': len(iou_results),
        'mean_iou': round(sum(r['iou'] for r in iou_results) / len(iou_results), 4) if iou_results else 0.0,
        'cohens_kappa': round(kappa, 4) if kappa is not None else None,
        'iou_matrix': iou_results,
    }
