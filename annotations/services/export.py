"""
Export annotations in COCO JSON, YOLO txt, and Pascal VOC XML formats.
"""
import json
import zipfile
from io import StringIO, BytesIO
from xml.etree import ElementTree as ET

from datasets.models import Dataset


def _get_dataset_annotations(dataset: Dataset):
    media_qs = dataset.media_files.prefetch_related(
        'annotations__class_label'
    ).all()
    return media_qs


# ── COCO ─────────────────────────────────────────────────────────────────────

def _ann_to_coco_entry(ann, ann_id: int, category_map: dict) -> dict:
    data = ann.data or {}
    if ann.type == 'bbox':
        x, y, w, h = data.get('x', 0), data.get('y', 0), data.get('w', 0), data.get('h', 0)
        return {
            'id': ann_id, 'image_id': ann.media_id,
            'category_id': category_map.get(ann.class_label_id, 1),
            'bbox': [x, y, w, h], 'area': w * h, 'segmentation': [], 'iscrowd': 0,
        }
    if ann.type in ('polygon', 'mask'):
        pts = data.get('points', [])
        xs, ys = pts[0::2], pts[1::2]
        if xs and ys:
            x, y = min(xs), min(ys)
            w, h = max(xs) - x, max(ys) - y
        else:
            x, y, w, h = 0, 0, 0, 0
        return {
            'id': ann_id, 'image_id': ann.media_id,
            'category_id': category_map.get(ann.class_label_id, 1),
            'bbox': [x, y, w, h], 'area': w * h,
            'segmentation': [pts] if pts else [], 'iscrowd': 0,
        }
    return {
        'id': ann_id, 'image_id': ann.media_id,
        'category_id': category_map.get(ann.class_label_id, 1),
        'bbox': [0, 0, 0, 0], 'area': 0, 'segmentation': [], 'iscrowd': 0,
    }


def export_coco(dataset: Dataset) -> dict:
    media_qs = _get_dataset_annotations(dataset)
    classes = list(dataset.project.classes.all())
    category_map = {c.id: idx + 1 for idx, c in enumerate(classes)}

    categories = [
        {'id': category_map[c.id], 'name': c.name, 'supercategory': 'object'}
        for c in classes
    ]

    images, annotations = [], []
    ann_id = 1

    for media in media_qs:
        images.append({
            'id': media.id,
            'file_name': media.original_filename or str(media.id),
            'width': media.width or 0,
            'height': media.height or 0,
        })
        for ann in media.annotations.all():
            entry = _ann_to_coco_entry(ann, ann_id, category_map)
            annotations.append(entry)
            ann_id += 1

    return {
        'info': {'description': dataset.name, 'version': str(dataset.version)},
        'categories': categories,
        'images': images,
        'annotations': annotations,
    }


# ── YOLO ─────────────────────────────────────────────────────────────────────

def export_yolo(dataset: Dataset) -> BytesIO:
    """Returns a zip archive with per-image .txt label files + classes.txt"""
    media_qs = _get_dataset_annotations(dataset)
    classes = list(dataset.project.classes.all())
    class_idx = {c.id: idx for idx, c in enumerate(classes)}

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        classes_txt = '\n'.join(c.name for c in classes)
        zf.writestr('classes.txt', classes_txt)

        for media in media_qs:
            lines = []
            w = media.width or 1
            h = media.height or 1
            for ann in media.annotations.filter(type='bbox'):
                data = ann.data or {}
                x, y, bw, bh = data.get('x', 0), data.get('y', 0), data.get('w', 0), data.get('h', 0)
                cx = (x + bw / 2) / w
                cy = (y + bh / 2) / h
                nw = bw / w
                nh = bh / h
                cls_id = class_idx.get(ann.class_label_id, 0)
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            fname = (media.original_filename or str(media.id)).rsplit('.', 1)[0] + '.txt'
            zf.writestr(f'labels/{fname}', '\n'.join(lines))

    buf.seek(0)
    return buf


# ── Pascal VOC ────────────────────────────────────────────────────────────────

def _annotation_to_voc(media, annotations) -> bytes:
    root = ET.Element('annotation')
    ET.SubElement(root, 'filename').text = media.original_filename or str(media.id)
    size = ET.SubElement(root, 'size')
    ET.SubElement(size, 'width').text = str(media.width or 0)
    ET.SubElement(size, 'height').text = str(media.height or 0)
    ET.SubElement(size, 'depth').text = '3'

    for ann in annotations:
        if ann.type != 'bbox':
            continue
        data = ann.data or {}
        x, y, w, h = data.get('x', 0), data.get('y', 0), data.get('w', 0), data.get('h', 0)
        obj = ET.SubElement(root, 'object')
        ET.SubElement(obj, 'name').text = ann.class_label.name
        ET.SubElement(obj, 'difficult').text = '0'
        bndbox = ET.SubElement(obj, 'bndbox')
        ET.SubElement(bndbox, 'xmin').text = str(int(x))
        ET.SubElement(bndbox, 'ymin').text = str(int(y))
        ET.SubElement(bndbox, 'xmax').text = str(int(x + w))
        ET.SubElement(bndbox, 'ymax').text = str(int(y + h))

    return ET.tostring(root, encoding='unicode')


def export_voc(dataset: Dataset) -> BytesIO:
    """Returns a zip archive with one XML file per image."""
    media_qs = _get_dataset_annotations(dataset)
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for media in media_qs:
            xml_str = _annotation_to_voc(media, list(media.annotations.all()))
            fname = (media.original_filename or str(media.id)).rsplit('.', 1)[0] + '.xml'
            zf.writestr(f'annotations/{fname}', xml_str)
    buf.seek(0)
    return buf
