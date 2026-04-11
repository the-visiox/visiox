
import os
import django
import requests

# Initialize Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'visiox.settings')
django.setup()

from projects.models import Project
from datasets.models import Dataset
from datasets.services.cvat import CVAT_HOST, CVAT_USERNAME, CVAT_PASSWORD

def pull_missing_tasks():
    print("Reconciling CVAT Tasks into VisioX...")
    
    session = requests.Session()
    session.auth = (CVAT_USERNAME, CVAT_PASSWORD)
    
    # Get all VisioX projects that are linked to CVAT
    projects = Project.objects.exclude(cvat_project_id__isnull=True)
    
    created_count = 0
    
    for project in projects:
        print(f"\nChecking Project: {project.name} (CVAT Project {project.cvat_project_id})")
        
        # Fetch tasks for this project from CVAT
        res = session.get(f"{CVAT_HOST}/api/tasks?project_id={project.cvat_project_id}")
        if res.status_code != 200:
            print(f"  [Error] Failed to fetch tasks from CVAT: {res.text}")
            continue
            
        cvat_tasks = res.json().get('results', [])
        print(f"  Found {len(cvat_tasks)} tasks in CVAT.")
        
        for task in cvat_tasks:
            task_id = task['id']
            task_name = task['name']
            
            # Check if this task already exists in VisioX
            dataset, created = Dataset.objects.get_or_create(
                cvat_task_id=task_id,
                defaults={
                    'project': project,
                    'name': task_name,
                    'version': 1
                }
            )
            
            if created:
                print(f"  [+] Imported new task: {task_name} (ID: {task_id})")
                created_count += 1
            else:
                # Optional: Ensure project is correct (healing)
                if dataset.project_id != project.id:
                    dataset.project = project
                    dataset.save()
                    print(f"  [~] Healed project link for: {task_name}")

    print(f"\n✅ Finished. Imported {created_count} missing tasks.")

if __name__ == "__main__":
    pull_missing_tasks()
