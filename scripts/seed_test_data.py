import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'visiox.settings')
django.setup()

from django.conf import settings
from teams.models import Team
from teams.models import TeamMember
from core.models.user import UserModel
from projects.models import Project
from datasets.models import Dataset, Media

user = UserModel.objects.filter(username='chunhattan2001').first()
if user is None:
    user = UserModel.objects.filter(email='demo@visiox.ai').first()
if user is None:
    user = UserModel.objects.create_user(
        username='demo',
        email='demo@visiox.ai',
        password='Demo1234!',
        first_name='Demo',
        last_name='User',
    )

team, _ = Team.objects.get_or_create(name='Test Workspace', defaults={'owner': user})
TeamMember.objects.get_or_create(team=team, user=user, defaults={'role': 'owner'})

demo_user = UserModel.objects.filter(email='demo@visiox.ai').first()
if demo_user is not None:
    TeamMember.objects.get_or_create(team=team, user=demo_user, defaults={'role': 'admin'})

base = os.path.join(settings.MEDIA_ROOT, 'media', '2026', '04', '03', 'demo')

projects_data = [
    {'folder': 'Cityscapes_Fine_Trai', 'name': 'Urban Scene Segmentation', 'task_type': 'semantic_segmentation'},
    {'folder': 'Factory_Floor_v1', 'name': 'Factory Floor Inspection v1', 'task_type': 'object_detection'},
    {'folder': 'Parking_Lot_v1', 'name': 'Parking Lot Detection', 'task_type': 'object_detection'},
    {'folder': 'NIH_ChestX-ray14_Sub', 'name': 'Medical Imaging - Chest X-ray', 'task_type': 'image_classification'},
    {'folder': 'PCB_Microscopy_Set_A', 'name': 'PCB Defect Inspector Set A', 'task_type': 'instance_segmentation'},
    {'folder': 'PCB_Microscopy_Set_B', 'name': 'PCB Defect Inspector Set B', 'task_type': 'instance_segmentation'},
    {'folder': 'Shelf_Images_', 'name': 'Retail Shelf Analytics', 'task_type': 'object_detection'},
    {'folder': 'Factory_Floor_v2_', 'name': 'Factory Floor Inspection v2', 'task_type': 'object_detection'},
]

all_folders = os.listdir(base)

for pd in projects_data:
    # Find matching folder. Prefer exact/prefix folder names before falling
    # back to a short prefix for folders with display punctuation.
    matching = [f for f in all_folders if f == pd['folder'] or f.startswith(pd['folder'])]
    if not matching:
        matching = [f for f in all_folders if f.startswith(pd['folder'][:14])]
    if not matching:
        print(f"Folder not found for prefix: {pd['folder'][:14]}")
        continue
    folder_name = matching[0]
    folder_path = os.path.join(base, folder_name)

    project, pcreated = Project.objects.get_or_create(
        name=pd['name'], team=team,
        defaults={'owner': user, 'task_type': pd['task_type'], 'description': f'Test dataset: {pd["name"]}'}
    )
    status = 'NEW' if pcreated else 'EXIST'
    print(f'Project [{status}]: {project.name}')

    dataset, dcreated = Dataset.objects.get_or_create(
        project=project, name=f'{pd["name"]} - v1',
        defaults={'description': 'Auto-generated test dataset', 'version': 1}
    )
    print(f'  Dataset [{"NEW" if dcreated else "EXIST"}]: {dataset.name}')

    image_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(image_exts)]
    print(f'  Found {len(files)} image files in {folder_name}')

    rel_prefix = '/'.join(['media', '2026', '04', '03', 'demo', folder_name])
    if dataset.media_files.exists() and not dataset.media_files.filter(file__startswith=rel_prefix).exists():
        removed, _ = dataset.media_files.all().delete()
        print(f'  Removed {removed} stale media records from a previous folder match')

    added = 0
    for fname in files[:15]:
        if Media.objects.filter(dataset=dataset, original_filename=fname).exists():
            continue
        fpath = os.path.join(folder_path, fname)
        fsize = os.path.getsize(fpath)
        rel_path = '/'.join([rel_prefix, fname])
        Media.objects.create(
            dataset=dataset,
            type='image',
            file=rel_path,
            original_filename=fname,
            file_size=fsize,
        )
        added += 1
    print(f'  Added {added} media records')

print('\nDone! Summary:')
print(f'  Projects in Test Workspace: {Project.objects.filter(team=team).count()}')
print(f'  Total datasets: {Dataset.objects.filter(project__team=team).count()}')
print(f'  Total media: {Media.objects.filter(dataset__project__team=team).count()}')
