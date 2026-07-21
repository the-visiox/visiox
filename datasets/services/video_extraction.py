from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from datasets.models import DatasetImportJob, Media


# Candidate density is deliberately internal. The user only chooses the desired
# output count; the worker samples enough frames to compare visual content.
CANDIDATES_PER_TARGET = 8
JPEG_QUALITY = 92

DEFAULT_VIDEO_EXTRACTION_CONFIG = {
    'enabled': True,
    'target': 200,
}


@dataclass(frozen=True)
class Candidate:
    timestamp: float
    bin_index: int
    descriptor: tuple[float, ...]
    sharpness: float
    brightness: float
    quality: float


def normalize_video_extraction_config(value: Any) -> dict:
    if value in (None, '', False):
        return {'enabled': False}
    if not isinstance(value, dict):
        raise ValueError('video_extraction must be a JSON object.')
    enabled = value.get('enabled', True)
    if not isinstance(enabled, bool):
        raise ValueError('video_extraction.enabled must be a boolean.')
    if not enabled:
        return {'enabled': False}

    raw_target = value.get('target', DEFAULT_VIDEO_EXTRACTION_CONFIG['target'])
    if isinstance(raw_target, bool):
        raise ValueError('video_extraction.target must be a number.')
    try:
        target = int(raw_target)
    except (TypeError, ValueError) as exc:
        raise ValueError('video_extraction.target must be a number.') from exc
    if not 1 <= target <= 2000:
        raise ValueError('video_extraction.target must be between 1 and 2000.')
    return {'enabled': True, 'target': target}


def build_timestamps(
    duration: float,
    target: int,
    candidates_per_target: int = CANDIDATES_PER_TARGET,
) -> list[tuple[float, int]]:
    """Distribute candidate timestamps across every output time bin."""
    timestamps: list[tuple[float, int]] = []
    bin_width = duration / target
    for bin_index in range(target):
        start = bin_index * bin_width
        for candidate_index in range(candidates_per_target):
            fraction = (candidate_index + 0.5) / candidates_per_target
            timestamp = min(start + fraction * bin_width, max(0.0, duration - 0.001))
            timestamps.append((timestamp, bin_index))
    return timestamps


def descriptor_distance(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    """Normalized Euclidean distance between two unit visual descriptors."""
    if len(first) != len(second):
        raise ValueError('Visual descriptors must have the same length.')
    return min(1.0, math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second))) / 2.0)


def select_diverse_candidates(candidates: list[Candidate], target: int) -> list[Candidate]:
    """Select one visually distinctive frame per time bin, then fill gaps.

    Temporal bins guarantee coverage across the full video. Inside each bin,
    the candidate furthest from all previously selected descriptors wins, with
    a small quality bonus to avoid preferring severely blurred/exposed frames.
    """
    if not candidates or target <= 0:
        return []

    by_bin: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        by_bin.setdefault(candidate.bin_index, []).append(candidate)

    selected: list[Candidate] = []
    selected_keys: set[tuple[float, int]] = set()

    def choose(items: list[Candidate]) -> Candidate:
        import numpy as np

        if not selected:
            return max(items, key=lambda item: item.quality)

        # A bounded, timeline-spanning anchor set avoids quadratic work on
        # requests containing hundreds or thousands of output frames.
        if len(selected) <= 64:
            anchors = selected
        else:
            anchor_indexes = np.linspace(0, len(selected) - 1, 64, dtype=int)
            anchors = [selected[index] for index in anchor_indexes]
        item_matrix = np.asarray([item.descriptor for item in items], dtype=np.float32)
        anchor_matrix = np.asarray([item.descriptor for item in anchors], dtype=np.float32)
        closest_similarity = np.max(item_matrix @ anchor_matrix.T, axis=1)
        visual_distance = np.sqrt(np.maximum(0.0, 2.0 - 2.0 * closest_similarity)) / 2.0
        scores = visual_distance + 0.12 * np.asarray([item.quality for item in items])
        return items[int(np.argmax(scores))]

    for bin_index in range(target):
        items = by_bin.get(bin_index, [])
        if not items:
            continue
        chosen = choose(items)
        selected.append(chosen)
        selected_keys.add((chosen.timestamp, chosen.bin_index))

    remaining = [
        candidate for candidate in candidates
        if (candidate.timestamp, candidate.bin_index) not in selected_keys
    ]
    while len(selected) < target and remaining:
        chosen = choose(remaining)
        selected.append(chosen)
        remaining.remove(chosen)

    return sorted(selected[:target], key=lambda item: item.timestamp)


def _read_frame(cap, timestamp: float):
    import cv2

    cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
    ok, frame = cap.read()
    return frame if ok else None


def _visual_features(frame) -> tuple[tuple[float, ...], float, float, float]:
    """Build a compact descriptor from color, layout and edge structure."""
    import cv2
    import numpy as np

    preview = cv2.resize(frame, (96, 96), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(preview, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(preview, cv2.COLOR_BGR2GRAY)

    color_hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).flatten()
    color_hist /= max(float(np.linalg.norm(color_hist)), 1e-8)

    layout = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    layout -= float(layout.mean())
    layout /= max(float(np.linalg.norm(layout)), 1e-8)

    edges = cv2.Canny(gray, 60, 150)
    edge_layout = cv2.resize(edges, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    edge_layout /= max(float(np.linalg.norm(edge_layout)), 1e-8)

    descriptor = np.concatenate((color_hist * 0.50, layout.flatten() * 0.30, edge_layout.flatten() * 0.20))
    descriptor /= max(float(np.linalg.norm(descriptor)), 1e-8)

    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    exposure_quality = max(0.0, 1.0 - abs(brightness - 127.5) / 127.5)
    sharpness_quality = min(1.0, math.log1p(sharpness) / math.log1p(500.0))
    quality = 0.55 * exposure_quality + 0.45 * sharpness_quality
    return tuple(float(value) for value in descriptor), sharpness, brightness, quality


def _inspect_video(path: str, duration: float, target: int, progress) -> tuple[list[Candidate], int]:
    import cv2

    timestamps = build_timestamps(duration, target)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError('Cannot open the uploaded video.')

    candidates: list[Candidate] = []
    read_failures = 0
    pending_progress = 0
    try:
        for timestamp, bin_index in timestamps:
            frame = _read_frame(cap, timestamp)
            if frame is None:
                read_failures += 1
            else:
                descriptor, sharpness, brightness, quality = _visual_features(frame)
                candidates.append(Candidate(
                    timestamp=timestamp,
                    bin_index=bin_index,
                    descriptor=descriptor,
                    sharpness=sharpness,
                    brightness=brightness,
                    quality=quality,
                ))
            pending_progress += 1
            if pending_progress >= 32:
                progress(pending_progress)
                pending_progress = 0
    finally:
        if pending_progress:
            progress(pending_progress)
        cap.release()
    return candidates, read_failures


def _video_metadata(path: str) -> tuple[float, float, int, int]:
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError('Cannot open the uploaded video.')
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if fps <= 0 or frame_count <= 0 or width <= 0 or height <= 0:
        raise RuntimeError('The uploaded video has invalid metadata.')
    return frame_count / fps, fps, width, height


def _safe_stem(name: str) -> str:
    stem = re.sub(r'[^A-Za-z0-9_-]+', '-', Path(name).stem).strip('-_') or 'video'
    return stem[:100]


def _timestamp_slug(timestamp: float) -> str:
    milliseconds = round(timestamp * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f'{hours:02d}-{minutes:02d}-{seconds:02d}-{millis:03d}'


def _save_selected_frames(
    job: DatasetImportJob,
    video_path: str,
    video_name: str,
    selected: list[Candidate],
) -> int:
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError('Cannot reopen the uploaded video.')
    saved = 0
    try:
        for index, candidate in enumerate(selected, start=1):
            frame = _read_frame(cap, candidate.timestamp)
            if frame is None:
                continue
            ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                continue
            filename = (
                f'{_safe_stem(video_name)}_job{job.id}_'
                f'{index:04d}_t{_timestamp_slug(candidate.timestamp)}.jpg'
            )
            media = Media(
                dataset=job.dataset,
                type='image',
                original_filename=filename,
                width=int(frame.shape[1]),
                height=int(frame.shape[0]),
                file_size=len(encoded),
                metadata={
                    'category': 'raw',
                    'import_format': 'video_extraction',
                    'import_job_id': job.id,
                    'source_video': video_name,
                    'timestamp_seconds': round(candidate.timestamp, 3),
                    'selection': {
                        'method': 'visual_diversity',
                        'sharpness': round(candidate.sharpness, 3),
                        'brightness': round(candidate.brightness, 3),
                        'quality': round(candidate.quality, 4),
                    },
                },
            )
            try:
                media.file.save(filename, ContentFile(encoded.tobytes()), save=False)
                thumb_scale = min(1.0, 400.0 / max(frame.shape[0], frame.shape[1]))
                thumbnail_frame = cv2.resize(
                    frame, None, fx=thumb_scale, fy=thumb_scale, interpolation=cv2.INTER_AREA,
                )
                thumb_ok, thumbnail = cv2.imencode(
                    '.jpg', thumbnail_frame, [cv2.IMWRITE_JPEG_QUALITY, 70],
                )
                if thumb_ok:
                    media.thumbnail.save(filename, ContentFile(thumbnail.tobytes()), save=False)
                media.save()
            except Exception:
                if media.file:
                    media.file.delete(save=False)
                if media.thumbnail:
                    media.thumbnail.delete(save=False)
                raise
            saved += 1
    finally:
        cap.release()
    return saved


def run_video_extraction_job(job: DatasetImportJob, config: dict) -> dict:
    videos = [item for item in (job.staged_files or []) if item.get('media_type') == 'video']
    if not videos:
        raise ValueError('Video extraction requires at least one uploaded video.')

    target = config['target']
    job.total = len(videos) * target * CANDIDATES_PER_TARGET
    job.done = 0
    job.save(update_fields=['total', 'done', 'updated_at'])

    def update_progress(amount: int) -> None:
        job.done = min(job.total, job.done + amount)
        job.save(update_fields=['done', 'updated_at'])

    results = []
    total_saved = 0
    for staged in videos:
        suffix = Path(staged.get('name') or 'video.mp4').suffix or '.mp4'
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as target_file:
                temp_path = target_file.name
                with default_storage.open(staged['key'], 'rb') as source:
                    shutil.copyfileobj(source, target_file, length=1024 * 1024)
            duration, fps, width, height = _video_metadata(temp_path)
            candidates, read_failures = _inspect_video(
                temp_path, duration, target, update_progress,
            )
            selected = select_diverse_candidates(candidates, target)
            saved = _save_selected_frames(
                job, temp_path, staged.get('name') or 'video.mp4', selected,
            )
            total_saved += saved
            results.append({
                'video': staged.get('name'),
                'duration_seconds': round(duration, 3),
                'fps': round(fps, 3),
                'width': width,
                'height': height,
                'inspected': len(candidates),
                'selected': len(selected),
                'saved': saved,
                'read_failures': read_failures,
            })
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass

    return {
        'format': 'video_extraction',
        'selection_method': 'visual_diversity',
        'files': total_saved,
        'source_videos': len(videos),
        'settings': config,
        'videos': results,
    }
