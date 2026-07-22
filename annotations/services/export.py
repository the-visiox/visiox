"""
Export dataset annotations in multiple formats.

Every exporter returns a ``BytesIO`` containing a ``.zip`` archive and accepts a
``save_images`` flag to optionally bundle the source images alongside the labels.

Supported formats: COCO, YOLO, Pascal VOC, segmentation mask, COCO keypoints,
ImageNet.
"""
import json
import zipfile
from io import BytesIO

from PIL import Image, ImageDraw
from xml.etree import ElementTree as ET

from datasets.models import Dataset


IMAGE_DIR = 'images'


# ── shared helpers ───────────────────────────────────────────────────────────

def _get_media(dataset: Dataset):
    return dataset.media_files.prefetch_related('annotations__class_label').all()


def _bbox(data: dict):
    """Return (x, y, w, h). Supports both {width,height} (native editor) and
    {w,h} (legacy/imported) payloads."""
    x = data.get('x', 0) or 0
    y = data.get('y', 0) or 0
    w = data.get('width', data.get('w', 0)) or 0
    h = data.get('height', data.get('h', 0)) or 0
    return x, y, w, h


def _bbox_from_points(pts):
    xs, ys = pts[0::2], pts[1::2]
    if not xs or not ys:
        return 0, 0, 0, 0
    x, y = min(xs), min(ys)
    return x, y, max(xs) - x, max(ys) - y


def _image_names(media_qs) -> dict:
    """media.id -> unique archive filename (keeps original names, de-dupes)."""
    names, seen = {}, set()
    for m in media_qs:
        base = m.original_filename or f"{m.id}.jpg"
        name = base
        if name in seen:
            stem, dot, ext = base.partition('.')
            name = f"{stem}_{m.id}{dot}{ext}"
        seen.add(name)
        names[m.id] = name
    return names


def _add_image(zf: zipfile.ZipFile, media, arcname: str, folder: str = IMAGE_DIR):
    """Copy a media file into the archive; silently skip if unreadable."""
    try:
        f = media.file.open('rb')
        try:
            zf.writestr(f"{folder}/{arcname}", f.read())
        finally:
            f.close()
    except Exception:
        pass


# ── COCO ─────────────────────────────────────────────────────────────────────

def _coco_entry(ann, ann_id: int, category_map: dict):
    data = ann.data or {}
    cid = category_map.get(ann.class_label_id, 1)
    if ann.type in ('bbox', 'rectangle'):
        x, y, w, h = _bbox(data)
        return {
            'id': ann_id, 'image_id': ann.media_id, 'category_id': cid,
            'bbox': [x, y, w, h], 'area': w * h, 'segmentation': [], 'iscrowd': 0,
        }
    if ann.type in ('polygon', 'mask'):
        pts = data.get('points', [])
        x, y, w, h = _bbox_from_points(pts)
        return {
            'id': ann_id, 'image_id': ann.media_id, 'category_id': cid,
            'bbox': [x, y, w, h], 'area': w * h,
            'segmentation': [pts] if pts else [], 'iscrowd': 0,
        }
    return None


def export_coco(dataset: Dataset, save_images: bool = False) -> BytesIO:
    media_qs = _get_media(dataset)
    names = _image_names(media_qs)
    classes = list(dataset.project.classes.all())
    category_map = {c.id: idx + 1 for idx, c in enumerate(classes)}
    categories = [
        {'id': category_map[c.id], 'name': c.name, 'supercategory': 'object'}
        for c in classes
    ]

    images, annotations = [], []
    ann_id = 1
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for m in media_qs:
            images.append({
                'id': m.id, 'file_name': names[m.id],
                'width': m.width or 0, 'height': m.height or 0,
            })
            for ann in m.annotations.all():
                entry = _coco_entry(ann, ann_id, category_map)
                if entry:
                    annotations.append(entry)
                    ann_id += 1
            if save_images:
                _add_image(zf, m, names[m.id])

        coco = {
            'info': {'description': dataset.name, 'version': str(dataset.version)},
            'categories': categories, 'images': images, 'annotations': annotations,
        }
        zf.writestr('annotations/instances.json', json.dumps(coco, indent=2))
    buf.seek(0)
    return buf


# ── YOLO ─────────────────────────────────────────────────────────────────────

def export_yolo(dataset: Dataset, save_images: bool = False) -> BytesIO:
    """classes.txt + per-image labels/<name>.txt (normalized bbox)."""
    media_qs = _get_media(dataset)
    names = _image_names(media_qs)
    classes = list(dataset.project.classes.all())
    class_idx = {c.id: idx for idx, c in enumerate(classes)}

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('classes.txt', '\n'.join(c.name for c in classes))
        for m in media_qs:
            w = m.width or 1
            h = m.height or 1
            lines = []
            for ann in m.annotations.all():
                if ann.type not in ('bbox', 'rectangle'):
                    continue
                bx, by, bw, bh = _bbox(ann.data or {})
                cx = (bx + bw / 2) / w
                cy = (by + bh / 2) / h
                cls_id = class_idx.get(ann.class_label_id, 0)
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw / w:.6f} {bh / h:.6f}")
            stem = names[m.id].rsplit('.', 1)[0]
            zf.writestr(f'labels/{stem}.txt', '\n'.join(lines))
            if save_images:
                _add_image(zf, m, names[m.id])
    buf.seek(0)
    return buf


# ── Pascal VOC ────────────────────────────────────────────────────────────────

def _voc_xml(media, filename: str) -> str:
    root = ET.Element('annotation')
    ET.SubElement(root, 'filename').text = filename
    size = ET.SubElement(root, 'size')
    ET.SubElement(size, 'width').text = str(media.width or 0)
    ET.SubElement(size, 'height').text = str(media.height or 0)
    ET.SubElement(size, 'depth').text = '3'

    for ann in media.annotations.all():
        if ann.type not in ('bbox', 'rectangle'):
            continue
        x, y, w, h = _bbox(ann.data or {})
        obj = ET.SubElement(root, 'object')
        ET.SubElement(obj, 'name').text = ann.class_label.name
        ET.SubElement(obj, 'difficult').text = '0'
        bndbox = ET.SubElement(obj, 'bndbox')
        ET.SubElement(bndbox, 'xmin').text = str(int(x))
        ET.SubElement(bndbox, 'ymin').text = str(int(y))
        ET.SubElement(bndbox, 'xmax').text = str(int(x + w))
        ET.SubElement(bndbox, 'ymax').text = str(int(y + h))

    return ET.tostring(root, encoding='unicode')


def export_voc(dataset: Dataset, save_images: bool = False) -> BytesIO:
    media_qs = _get_media(dataset)
    names = _image_names(media_qs)
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for m in media_qs:
            stem = names[m.id].rsplit('.', 1)[0]
            zf.writestr(f'Annotations/{stem}.xml', _voc_xml(m, names[m.id]))
            if save_images:
                _add_image(zf, m, names[m.id], folder='JPEGImages')
    buf.seek(0)
    return buf


# ── Segmentation mask ──────────────────────────────────────────────────────────

def export_segmentation_mask(dataset: Dataset, save_images: bool = False) -> BytesIO:
    """Grayscale index masks (PNG) from polygons + boxes, plus labelmap.txt.

    Pixel value 0 = background; each class maps to its 1-based index."""
    media_qs = _get_media(dataset)
    names = _image_names(media_qs)
    classes = list(dataset.project.classes.all())
    idx = {c.id: i + 1 for i, c in enumerate(classes)}

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        labelmap = ['0 background'] + [f'{idx[c.id]} {c.name}' for c in classes]
        zf.writestr('labelmap.txt', '\n'.join(labelmap))

        for m in media_qs:
            w, h = m.width or 0, m.height or 0
            if not w or not h:
                continue
            mask = Image.new('L', (w, h), 0)
            draw = ImageDraw.Draw(mask)
            for ann in m.annotations.all():
                value = idx.get(ann.class_label_id, 0)
                if not value:
                    continue
                if ann.type in ('polygon', 'mask'):
                    pts = (ann.data or {}).get('points', [])
                    if len(pts) >= 6:
                        draw.polygon(list(zip(pts[0::2], pts[1::2])), fill=value)
                elif ann.type in ('bbox', 'rectangle'):
                    bx, by, bw, bh = _bbox(ann.data or {})
                    draw.rectangle([bx, by, bx + bw, by + bh], fill=value)
            png = BytesIO()
            mask.save(png, format='PNG')
            stem = names[m.id].rsplit('.', 1)[0]
            zf.writestr(f'masks/{stem}.png', png.getvalue())
            if save_images:
                _add_image(zf, m, names[m.id])
    buf.seek(0)
    return buf


# ── COCO Keypoints ─────────────────────────────────────────────────────────────

def export_coco_keypoints(dataset: Dataset, save_images: bool = False) -> BytesIO:
    media_qs = _get_media(dataset)
    names = _image_names(media_qs)
    classes = list(dataset.project.classes.all())
    category_map = {c.id: idx + 1 for idx, c in enumerate(classes)}

    # Keypoint count per class = the largest point set seen for that class.
    max_kp = {c.id: 0 for c in classes}
    for m in media_qs:
        for ann in m.annotations.all():
            if ann.type in ('point', 'keypoint'):
                n = len((ann.data or {}).get('points', [])) // 2
                max_kp[ann.class_label_id] = max(max_kp.get(ann.class_label_id, 0), n)

    categories = [
        {
            'id': category_map[c.id], 'name': c.name, 'supercategory': 'object',
            'keypoints': [f'kp_{i + 1}' for i in range(max_kp.get(c.id, 0))],
            'skeleton': [],
        }
        for c in classes
    ]

    images, annotations = [], []
    ann_id = 1
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for m in media_qs:
            images.append({
                'id': m.id, 'file_name': names[m.id],
                'width': m.width or 0, 'height': m.height or 0,
            })
            for ann in m.annotations.all():
                if ann.type not in ('point', 'keypoint'):
                    continue
                pts = (ann.data or {}).get('points', [])
                if len(pts) < 2:
                    continue
                n = max_kp.get(ann.class_label_id, 0)
                kps = []
                for i in range(n):
                    if i * 2 + 1 < len(pts):
                        kps += [pts[i * 2], pts[i * 2 + 1], 2]
                    else:
                        kps += [0, 0, 0]
                x, y, w, h = _bbox_from_points(pts)
                annotations.append({
                    'id': ann_id, 'image_id': m.id,
                    'category_id': category_map.get(ann.class_label_id, 1),
                    'keypoints': kps, 'num_keypoints': len(pts) // 2,
                    'bbox': [x, y, w, h], 'area': w * h,
                    'iscrowd': 0, 'segmentation': [],
                })
                ann_id += 1
            if save_images:
                _add_image(zf, m, names[m.id])

        coco = {
            'info': {'description': dataset.name, 'version': str(dataset.version)},
            'categories': categories, 'images': images, 'annotations': annotations,
        }
        zf.writestr('annotations/person_keypoints.json', json.dumps(coco, indent=2))
    buf.seek(0)
    return buf


# ── ImageNet ────────────────────────────────────────────────────────────────────

def export_imagenet(dataset: Dataset, save_images: bool = False) -> BytesIO:
    """Classification layout from tag annotations: labels.txt mapping plus, when
    requested, images grouped into one folder per class (<class>/<file>)."""
    media_qs = _get_media(dataset)
    names = _image_names(media_qs)

    buf = BytesIO()
    labels = []
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for m in media_qs:
            tag_classes = []
            for ann in m.annotations.all():
                if ann.type == 'tag':
                    name = ann.class_label.name
                    if name not in tag_classes:
                        tag_classes.append(name)
            for name in tag_classes:
                labels.append(f"{names[m.id]} {name}")
                if save_images:
                    _add_image(zf, m, names[m.id], folder=name)
        zf.writestr('labels.txt', '\n'.join(labels))
    buf.seek(0)
    return buf
