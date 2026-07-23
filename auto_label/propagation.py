import math


MATCH_SCALES = (0.9, 1.0, 1.1)
MIN_TEMPLATE_SIZE = 8
LOCAL_SEARCH_EXPANSION = 3.0
LOCAL_SEARCH_PADDING = 16
MAX_GLOBAL_SEARCH_PIXELS = 1280 * 720


def normalize_bbox(value, *, image_width=None, image_height=None):
    if not isinstance(value, dict):
        raise ValueError('bbox must be an object with x, y, width and height.')
    try:
        x = float(value['x'])
        y = float(value['y'])
        width = float(value['width'])
        height = float(value['height'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('bbox must contain numeric x, y, width and height.') from exc
    if not all(math.isfinite(item) for item in (x, y, width, height)) or width <= 1 or height <= 1:
        raise ValueError('bbox must have finite coordinates and a positive size.')
    if image_width and image_height:
        x = max(0.0, min(x, float(image_width)))
        y = max(0.0, min(y, float(image_height)))
        width = max(0.0, min(width, float(image_width) - x))
        height = max(0.0, min(height, float(image_height) - y))
        if width <= 1 or height <= 1:
            raise ValueError('bbox is outside the source image.')
    return {'x': x, 'y': y, 'width': width, 'height': height}


def bbox_iou(left, right):
    left_x2 = left['x'] + left['width']
    left_y2 = left['y'] + left['height']
    right_x2 = right['x'] + right['width']
    right_y2 = right['y'] + right['height']
    intersection_width = max(0.0, min(left_x2, right_x2) - max(left['x'], right['x']))
    intersection_height = max(0.0, min(left_y2, right_y2) - max(left['y'], right['y']))
    intersection = intersection_width * intersection_height
    union = left['width'] * left['height'] + right['width'] * right['height'] - intersection
    return intersection / union if union > 0 else 0.0


def read_media_image(media):
    import cv2
    import numpy as np

    if not media.file:
        return None
    with media.file.open('rb') as source:
        return cv2.imdecode(np.frombuffer(source.read(), dtype=np.uint8), cv2.IMREAD_COLOR)


def crop_bbox(image, bbox):
    height, width = image.shape[:2]
    x1 = max(0, min(width - 1, int(round(bbox['x']))))
    y1 = max(0, min(height - 1, int(round(bbox['y']))))
    x2 = max(x1 + 1, min(width, int(round(bbox['x'] + bbox['width']))))
    y2 = max(y1 + 1, min(height, int(round(bbox['y'] + bbox['height']))))
    return image[y1:y2, x1:x2].copy()


def _search_region(image, bbox):
    height, width = image.shape[:2]
    center_x = bbox['x'] + bbox['width'] / 2
    center_y = bbox['y'] + bbox['height'] / 2
    search_width = max(
        bbox['width'] * LOCAL_SEARCH_EXPANSION,
        bbox['width'] + LOCAL_SEARCH_PADDING,
    )
    search_height = max(
        bbox['height'] * LOCAL_SEARCH_EXPANSION,
        bbox['height'] + LOCAL_SEARCH_PADDING,
    )
    x1 = max(0, int(center_x - search_width / 2))
    y1 = max(0, int(center_y - search_height / 2))
    x2 = min(width, int(math.ceil(center_x + search_width / 2)))
    y2 = min(height, int(math.ceil(center_y + search_height / 2)))
    return image[y1:y2, x1:x2], x1, y1


def _resize_global_search(search, template):
    import cv2

    pixel_count = search.shape[0] * search.shape[1]
    if pixel_count <= MAX_GLOBAL_SEARCH_PIXELS:
        return search, template, 1.0

    coordinate_scale = math.sqrt(MAX_GLOBAL_SEARCH_PIXELS / pixel_count)
    search_size = (
        max(1, int(round(search.shape[1] * coordinate_scale))),
        max(1, int(round(search.shape[0] * coordinate_scale))),
    )
    template_size = (
        max(MIN_TEMPLATE_SIZE, int(round(template.shape[1] * coordinate_scale))),
        max(MIN_TEMPLATE_SIZE, int(round(template.shape[0] * coordinate_scale))),
    )
    return (
        cv2.resize(search, search_size, interpolation=cv2.INTER_AREA),
        cv2.resize(template, template_size, interpolation=cv2.INTER_AREA),
        coordinate_scale,
    )


def _match_at_scale(img_gray, template, scale):
    import cv2

    template_width = max(MIN_TEMPLATE_SIZE, int(round(template.shape[1] * scale)))
    template_height = max(MIN_TEMPLATE_SIZE, int(round(template.shape[0] * scale)))
    if template_width > img_gray.shape[1] or template_height > img_gray.shape[0]:
        return None

    resized = cv2.resize(template, (template_width, template_height), interpolation=cv2.INTER_AREA)
    template_gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    scores = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(scores)
    if not math.isfinite(score):
        return None
    return float(score), location, template_width, template_height


def _best_match(image, template, search_bbox=None):
    import cv2

    if search_bbox is None:
        search, template, coordinate_scale = _resize_global_search(image, template)
        offset_x = offset_y = 0
    else:
        search, offset_x, offset_y = _search_region(image, search_bbox)
        coordinate_scale = 1.0
    if search.size == 0 or template.size == 0:
        return None

    img_gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    best = None
    for scale in MATCH_SCALES:
        match = _match_at_scale(img_gray, template, scale)
        if match is None:
            continue
        score, location, template_width, template_height = match
        candidate = {
            'x': float(offset_x + location[0] / coordinate_scale),
            'y': float(offset_y + location[1] / coordinate_scale),
            'width': float(template_width / coordinate_scale),
            'height': float(template_height / coordinate_scale),
        }
        if best is None or score > best[0]:
            best = score, candidate
    return best


def track_next_bbox(image, previous_bbox, previous_template, seed_template, threshold):
    local = _best_match(image, previous_template, previous_bbox)
    candidate = local
    if candidate is None or candidate[0] < threshold:
        global_match = _best_match(image, seed_template)
        if global_match is not None and (candidate is None or global_match[0] > candidate[0]):
            candidate = global_match
    if candidate is None or candidate[0] < threshold:
        return None
    score, bbox = candidate
    return bbox, max(0.0, min(1.0, score)), crop_bbox(image, bbox)
