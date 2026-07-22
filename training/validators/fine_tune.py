from rest_framework import serializers


def validate_architecture_task(architecture, project):
    if architecture and project and architecture.task_type != project.task_type:
        raise serializers.ValidationError({
            'architecture': f'This architecture is for {architecture.task_type}, not {project.task_type}.'
        })


def validate_fine_tune(initialization_mode, base_model, project, architecture):
    if initialization_mode != 'fine_tune':
        return None
    if base_model is None:
        raise serializers.ValidationError({
            'base_model': 'Select a completed PyTorch model to fine-tune from.'
        })

    parent_job = base_model.training_job
    if base_model.format != 'pytorch' or not base_model.model_file:
        raise serializers.ValidationError({
            'base_model': 'Fine-tuning currently requires a registered PyTorch .pt model.'
        })
    if parent_job is None or parent_job.status != 'completed':
        raise serializers.ValidationError({
            'base_model': 'The source model must belong to a completed training run.'
        })
    if project and parent_job.project_id != project.id:
        raise serializers.ValidationError({
            'base_model': 'The source model must belong to the selected project.'
        })
    if architecture and parent_job.architecture_id != architecture.id:
        raise serializers.ValidationError({
            'architecture': 'Use the same architecture as the source training run.'
        })

    current_schema = list(project.classes.order_by('index', 'id').values('id', 'name')) if project else []
    parent_names = [item.get('name') for item in (parent_job.class_schema or [])]
    current_names = [item['name'] for item in current_schema]
    if parent_names and parent_names != current_names:
        raise serializers.ValidationError({
            'base_model': (
                'Project classes changed after the source run. '
                'Restore the original class order before fine-tuning.'
            )
        })
    return parent_job
