
import os
import django
import requests

# Initialize Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'visiox.settings')
django.setup()

from projects.models import Project
from datasets.services.cvat import CVAT_HOST, CVAT_USERNAME, CVAT_PASSWORD

def update_webhooks():
    print("Updating CVAT Webhooks to include 'create' and 'delete' events...")
    
    WEBHOOK_URL = "http://host.docker.internal:8000/api/datasets/cvat-webhook/"
    session = requests.Session()
    session.auth = (CVAT_USERNAME, CVAT_PASSWORD)
    
    # Get all webhooks
    res = session.get(f"{CVAT_HOST}/api/webhooks")
    if res.status_code != 200:
        print(f"Failed to fetch webhooks: {res.text}")
        return

    webhooks = res.json().get('results', [])
    updated_count = 0
    
    for wh in webhooks:
        if wh['target_url'] == WEBHOOK_URL:
            # Update specific events
            target_events = ["create:task", "update:task", "update:job", "delete:task"]
            if set(wh['events']) != set(target_events):
                print(f"Updating Webhook ID {wh['id']} for Project {wh.get('project_id')}...")
                update_res = session.patch(f"{CVAT_HOST}/api/webhooks/{wh['id']}", json={
                    "events": target_events
                })
                if update_res.status_code in [200, 201]:
                    print("  [OK] Successfully updated.")
                    updated_count += 1
                else:
                    print(f"  [Error] Failed to update: {update_res.text}")
    
    print(f"\nUpdate finished. {updated_count} webhooks modernized.")

if __name__ == "__main__":
    update_webhooks()
