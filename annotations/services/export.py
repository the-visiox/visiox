import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image, ImageDraw
from xml.etree import ElementTree as ET

from datasets.models import Dataset


IMAGE_DIR = 'images'


# ── shared helpers ───────────────────────────────────────────────────────────

def _get_media(dataset: Dataset):
    return dataset.media_files.prefetch_related('annotations__class_label').all()


def _bbox(data: dict):
    # Return (x, y, w, h). Supports both {width,height} and {w,h} payloads.
    x = data.get('x', 0) or 0
    y = data.get('y', 0) or 0
    w = data.get('width', data.get('w', 0)) or 0
    h = data.get('height', data.get('h', 0)) or 0
    return x, y, w, h


def _bbox_from_points(pts):
    xs, pts_ys = pts[0::2], pts[1::2]
    if not xs or not pts_ys:
        return 0, 0, 0, 0
    x, y = min(xs), min(pts_ys)
    return x, y, max(xs) - x, max(pts_ys) - y


def _image_names(media_qs) -> dict:
    # media.id -> unique archive filename (keeps original names, de-dupes).
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


def _read_media_bytes(media) -> bytes | None:
    try:
        f = media.file.open('rb')
        try:
            return f.read()
        finally:
            f.close()
    except Exception:
        return None


def _preload_media_data(media_qs) -> dict:
    # Fetch media files concurrently to eliminate serial network/disk latency.
    media_list = list(media_qs)
    if not media_list:
        return {}

    if len(media_list) <= 2:
        results = {}
        for m in media_list:
            b = _read_media_bytes(m)
            if b is not None:
                results[m.id] = b
        return results

    results = {}
    max_workers = min(16, (os.cpu_count() or 4) * 4)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(_read_media_bytes, m): m.id for m in media_list}
        for future in future_map:
            mid = future_map[future]
            try:
                content = future.result()
                if content is not None:
                    results[mid] = content
            except Exception:
                pass
    return results


def _add_image(zf: zipfile.ZipFile, media, arcname: str, folder: str = IMAGE_DIR, data: bytes | None = None):
    # Copy media into archive with ZIP_STORED because images are already compressed.
    try:
        content = data if data is not None else _read_media_bytes(media)
        if content is not None:
            zf.writestr(f"{folder}/{arcname}", content, compress_type=zipfile.ZIP_STORED)
    except Exception:
        pass


def _yolo_lines(media, class_idx: dict) -> list[str]:
    width = media.width or 1
    height = media.height or 1
    lines = []
    for ann in media.annotations.all():
        if ann.type not in ('bbox', 'rectangle'):
            continue
        bx, by, bw, bh = _bbox(ann.data or {})
        cx = (bx + bw / 2) / width
        cy = (by + bh / 2) / height
        cls_id = class_idx.get(ann.class_label_id, 0)
        lines.append(
            f"{cls_id} {cx:.6f} {cy:.6f} "
            f"{bw / width:.6f} {bh / height:.6f}"
        )
    return lines


def _yolo_data_yaml(classes, include_test: bool) -> str:
    lines = [
        'path: .',
        'train: train/images',
        'val: valid/images',
    ]
    if include_test:
        lines.append('test: test/images')
    lines.extend(['', f'nc: {len(classes)}', 'names:'])
    lines.extend(
        f'  {index}: {json.dumps(label.name, ensure_ascii=False)}'
        for index, label in enumerate(classes)
    )
    return '\n'.join(lines) + '\n'


def _yolo_data_yaml_flat(classes) -> str:
    lines = [
        'path: .',
        'train: images',
        'val: images',
        '',
        f'nc: {len(classes)}',
        'names:',
    ]
    lines.extend(
        f'  {index}: {json.dumps(label.name, ensure_ascii=False)}'
        for index, label in enumerate(classes)
    )
    return '\n'.join(lines) + '\n'


def _fixed_test_media(dataset: Dataset):
    test_dataset_id = (dataset.split_config or {}).get('test_dataset_id')
    if not test_dataset_id:
        return []
    try:
        test_dataset = Dataset.objects.get(pk=test_dataset_id, project=dataset.project)
    except Dataset.DoesNotExist:
        return []
    return [
        media
        for media in _get_media(test_dataset).filter(type='image').exclude(file='')
        if (media.metadata or {}).get('category') != 'augmented'
    ]


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
    media_data = _preload_media_data(media_qs) if save_images else {}
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
                _add_image(zf, m, names[m.id], data=media_data.get(m.id))

        coco = {
            'info': {'description': dataset.name, 'version': str(dataset.version)},
            'categories': categories, 'images': images, 'annotations': annotations,
        }
        zf.writestr('annotations/instances.json', json.dumps(coco, indent=2))
    buf.seek(0)
    return buf


# ── YOLO ─────────────────────────────────────────────────────────────────────

def export_yolo(dataset: Dataset, save_images: bool = False) -> BytesIO:
    media_qs = _get_media(dataset)
    fixed_test = _fixed_test_media(dataset)
    all_media = list(media_qs) + (list(fixed_test) if fixed_test else [])
    media_data = _preload_media_data(all_media) if save_images else {}
    names = _image_names(media_qs)
    classes = list(dataset.project.classes.all())
    class_idx = {c.id: idx for idx, c in enumerate(classes)}

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('classes.txt', '\n'.join(c.name for c in classes))

        split_media = {'train': [], 'val': [], 'test': []}
        for m in media_qs:
            split = (m.metadata or {}).get('split')
            if split in split_media:
                split_media[split].append(m)

        has_split = bool(dataset.split_config) and bool(
            split_media['train'] or split_media['val'] or split_media['test'] or fixed_test
        )
        if has_split:
            if fixed_test:
                split_media['test'] = fixed_test
            split_names = {'train': 'train', 'val': 'valid', 'test': 'test'}
            for split, folder in split_names.items():
                members = split_media[split]
                member_names = names if split != 'test' or not fixed_test else _image_names(members)
                if members:
                    zf.writestr(f'{folder}/images/', '')
                    zf.writestr(f'{folder}/labels/', '')
                for m in members:
                    filename = member_names[m.id]
                    stem = filename.rsplit('.', 1)[0]
                    label_lines = _yolo_lines(m, class_idx)
                    zf.writestr(f'{folder}/labels/{stem}.txt', '\n'.join(label_lines))
                    if save_images:
                        _add_image(zf, m, filename, folder=f'{folder}/images', data=media_data.get(m.id))
            zf.writestr('data.yaml', _yolo_data_yaml(classes, bool(split_media['test'])))
        else:
            for m in media_qs:
                label_lines = _yolo_lines(m, class_idx)
                stem = names[m.id].rsplit('.', 1)[0]
                zf.writestr(f'labels/{stem}.txt', '\n'.join(label_lines))
                if save_images:
                    _add_image(zf, m, names[m.id], data=media_data.get(m.id))
            zf.writestr('data.yaml', _yolo_data_yaml_flat(classes))
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
    media_data = _preload_media_data(media_qs) if save_images else {}
    names = _image_names(media_qs)
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for m in media_qs:
            stem = names[m.id].rsplit('.', 1)[0]
            zf.writestr(f'Annotations/{stem}.xml', _voc_xml(m, names[m.id]))
            if save_images:
                _add_image(zf, m, names[m.id], folder='JPEGImages', data=media_data.get(m.id))
    buf.seek(0)
    return buf


# ── Segmentation mask ──────────────────────────────────────────────────────────

def export_segmentation_mask(dataset: Dataset, save_images: bool = False) -> BytesIO:
    media_qs = _get_media(dataset)
    media_data = _preload_media_data(media_qs) if save_images else {}
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
                _add_image(zf, m, names[m.id], data=media_data.get(m.id))
    buf.seek(0)
    return buf


# ── COCO Keypoints ─────────────────────────────────────────────────────────────

def export_coco_keypoints(dataset: Dataset, save_images: bool = False) -> BytesIO:
    media_qs = _get_media(dataset)
    media_data = _preload_media_data(media_qs) if save_images else {}
    names = _image_names(media_qs)
    classes = list(dataset.project.classes.all())
    category_map = {c.id: idx + 1 for idx, c in enumerate(classes)}

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
                _add_image(zf, m, names[m.id], data=media_data.get(m.id))

        coco = {
            'info': {'description': dataset.name, 'version': str(dataset.version)},
            'categories': categories, 'images': images, 'annotations': annotations,
        }
        zf.writestr('annotations/person_keypoints.json', json.dumps(coco, indent=2))
    buf.seek(0)
    return buf


# ── ImageNet ────────────────────────────────────────────────────────────────────

def export_imagenet(dataset: Dataset, save_images: bool = False) -> BytesIO:
    media_qs = _get_media(dataset)
    media_data = _preload_media_data(media_qs) if save_images else {}
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
                    _add_image(zf, m, names[m.id], folder=name, data=media_data.get(m.id))
        zf.writestr('labels.txt', '\n'.join(labels))
    buf.seek(0)
    return buf
