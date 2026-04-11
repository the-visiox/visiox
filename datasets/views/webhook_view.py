import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from datasets.models import Dataset
from projects.models import Project

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def cvat_webhook(request):
    """
    Receive webhooks from CVAT and keep VisioX datasets in sync.

    Events handled:
      - create:task  → create a Dataset if missing
      - delete:task  → delete the linked Dataset
      - update:task / update:job → bump dataset version
    """
    event = request.data.get('event')
    task_data = request.data.get('task', {})
    job_data = request.data.get('job', {})

    task_id = task_data.get('id') or job_data.get('task_id')
    if not task_id:
        return Response({'detail': 'No task ID in payload'}, status=status.HTTP_400_BAD_REQUEST)

    logger.info('CVAT webhook: event=%s task_id=%s', event, task_id)

    try:
        if event == 'create:task':
            return _handle_task_created(task_id, task_data)

        dataset = Dataset.objects.get(cvat_task_id=task_id)

        if event == 'delete:task':
            logger.info('Deleting dataset %d (%s) due to CVAT task deletion', dataset.id, dataset.name)
            dataset.delete()
            return Response({'status': 'deleted'})

        dataset.version += 1
        dataset.save(update_fields=['version', 'updated_at'])
        return Response({'status': 'acknowledged', 'dataset': dataset.id})

    except Dataset.DoesNotExist:
        return Response({'detail': 'Dataset not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        logger.exception('Unhandled error in CVAT webhook (event=%s, task=%s)', event, task_id)
        return Response({'error': 'Internal error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _handle_task_created(task_id: int, task_data: dict):
    project_id = task_data.get('project_id')
    try:
        project = Project.objects.get(cvat_project_id=project_id)
    except Project.DoesNotExist:
        return Response(
            {'detail': 'Linked project not found in VisioX'},
            status=status.HTTP_404_NOT_FOUND,
        )

    dataset, created = Dataset.objects.get_or_create(
        cvat_task_id=task_id,
        defaults={
            'project': project,
            'name': task_data.get('name', f'CVAT Task {task_id}'),
        },
    )
    if created:
        logger.info('Auto-created dataset %d from CVAT task %d', dataset.id, task_id)

    return Response(
        {'status': 'created', 'dataset': dataset.id},
        status=status.HTTP_201_CREATED,
    )
