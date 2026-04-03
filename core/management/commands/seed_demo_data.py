"""
python manage.py seed_demo_data

Creates a realistic demo workspace:
  - 1 demo user  (demo@visiox.ai / Demo1234!)
  - 2 teams      (VisioX Demo Lab, Edge AI Team)
  - 6 projects   (object detection, classification, segmentation, …)
  - 8 datasets
  - 5 model architectures (YOLOv8n/s/m, ResNet-50, ViT-B)
  - 8 training jobs with experiments + metrics
  - 4 model registry entries
  - 3 inference endpoints
  - billing plans + subscription

Run setup_groups first to create role_* Groups:
  python manage.py setup_groups && python manage.py seed_demo_data
"""

import random
import urllib.request
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()

DEMO_EMAIL = "demo@visiox.ai"
DEMO_PASSWORD = "Demo1234!"


def _rand_metrics(epoch: int, base_loss: float = 2.0) -> dict:
    decay = 1 - (epoch / 120)
    return {
        "loss": round(base_loss * decay + random.uniform(0, 0.1), 4),
        "val_loss": round(base_loss * decay + random.uniform(0.05, 0.2), 4),
        "map50": round(min(0.95, 0.3 + (epoch / 120) * 0.65 + random.uniform(-0.02, 0.02)), 4),
        "map75": round(min(0.85, 0.2 + (epoch / 120) * 0.6 + random.uniform(-0.02, 0.02)), 4),
        "f1": round(min(0.95, 0.25 + (epoch / 120) * 0.7 + random.uniform(-0.01, 0.01)), 4),
        "accuracy": round(min(0.99, 0.4 + (epoch / 120) * 0.58 + random.uniform(-0.01, 0.01)), 4),
    }


class Command(BaseCommand):
    help = "Seed the database with realistic VisioX demo data (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo data before re-seeding.",
        )
        parser.add_argument(
            "--skip-media",
            action="store_true",
            help="Skip downloading sample images (faster, but datasets will be empty).",
        )
        parser.add_argument(
            "--images-per-dataset",
            type=int,
            default=12,
            help="Number of sample images to download per dataset (default: 12).",
        )

    def handle(self, *args, **options):
        from annotations.models import Annotation, Class
        from billing.models import Plan, Subscription
        from datasets.models import Dataset
        from deployments.models import InferenceEndpoint, ModelRegistry
        from projects.models import Project
        from teams.models import Team, TeamMember
        from training.models import Experiment, ModelArchitecture, RunMetric, TrainingJob

        if options["reset"]:
            self.stdout.write(self.style.WARNING("Resetting existing demo data…"))
            User.objects.filter(email=DEMO_EMAIL).delete()
            Team.objects.filter(name__in=["VisioX Demo Lab", "Edge AI Team"]).delete()
            ModelArchitecture.objects.filter(is_builtin=True).delete()
            Plan.objects.filter(name__in=["Starter", "Professional", "Enterprise"]).delete()

        # ── 1. Demo user ────────────────────────────────────────────────
        user, created = User.objects.get_or_create(
            email=DEMO_EMAIL,
            defaults={
                "username": "demo",
                "first_name": "Demo",
                "last_name": "User",
                "is_active": True,
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}"))
        else:
            self.stdout.write(f"Demo user already exists: {DEMO_EMAIL}")

        # ── 2. Billing plans ────────────────────────────────────────────
        plan_starter, _ = Plan.objects.get_or_create(
            name="Starter",
            defaults={
                "description": "For individuals and small experiments.",
                "price_usd": "0.00",
                "billing_period": "monthly",
                "storage_gb": 5,
                "max_seats": 1,
                "gpu_hours_monthly": 5,
                "is_active": True,
            },
        )
        plan_pro, _ = Plan.objects.get_or_create(
            name="Professional",
            defaults={
                "description": "For teams with production workloads.",
                "price_usd": "79.00",
                "billing_period": "monthly",
                "storage_gb": 100,
                "max_seats": 10,
                "gpu_hours_monthly": 50,
                "is_active": True,
            },
        )
        Plan.objects.get_or_create(
            name="Enterprise",
            defaults={
                "description": "Unlimited scale with dedicated support.",
                "price_usd": "499.00",
                "billing_period": "monthly",
                "storage_gb": 10000,
                "max_seats": 1000,
                "gpu_hours_monthly": 1000,
                "is_active": True,
            },
        )
        self.stdout.write("Billing plans ready.")

        # ── 3. Model architectures ──────────────────────────────────────
        arch_defs = [
            {
                "name": "YOLOv8n",
                "backbone": "CSPDarkNet-nano",
                "task_type": "object_detection",
                "description": "Nano variant — fastest inference, ideal for edge devices.",
                "default_config": {"epochs": 100, "imgsz": 640, "batch": 16, "lr0": 0.01},
            },
            {
                "name": "YOLOv8s",
                "backbone": "CSPDarkNet-small",
                "task_type": "object_detection",
                "description": "Small variant — balanced speed and accuracy.",
                "default_config": {"epochs": 100, "imgsz": 640, "batch": 16, "lr0": 0.01},
            },
            {
                "name": "YOLOv8m",
                "backbone": "CSPDarkNet-medium",
                "task_type": "object_detection",
                "description": "Medium variant — higher mAP, moderate GPU requirements.",
                "default_config": {"epochs": 150, "imgsz": 640, "batch": 8, "lr0": 0.008},
            },
            {
                "name": "ResNet-50",
                "backbone": "ResNet-50",
                "task_type": "image_classification",
                "description": "Proven 50-layer residual network for image classification.",
                "default_config": {"epochs": 90, "imgsz": 224, "batch": 64, "lr0": 0.001},
            },
            {
                "name": "ViT-B/16",
                "backbone": "Vision Transformer Base",
                "task_type": "image_classification",
                "description": "Vision Transformer — state-of-the-art accuracy on large datasets.",
                "default_config": {"epochs": 120, "imgsz": 224, "batch": 32, "lr0": 0.0003},
            },
            {
                "name": "Mask R-CNN",
                "backbone": "ResNet-101-FPN",
                "task_type": "instance_segmentation",
                "description": "Extends Faster R-CNN with a mask prediction branch.",
                "default_config": {"epochs": 100, "imgsz": 800, "batch": 4, "lr0": 0.005},
            },
            {
                "name": "DeepLabV3+",
                "backbone": "ResNet-101",
                "task_type": "semantic_segmentation",
                "description": "ASPP + Decoder for high-resolution semantic segmentation.",
                "default_config": {"epochs": 80, "imgsz": 512, "batch": 8, "lr0": 0.001},
            },
        ]
        architectures = {}
        for a in arch_defs:
            obj, _ = ModelArchitecture.objects.get_or_create(
                name=a["name"],
                defaults={k: v for k, v in a.items() if k != "name"},
            )
            architectures[a["name"]] = obj
        self.stdout.write(f"Model architectures ready ({len(architectures)}).")

        # ── 4. Teams ────────────────────────────────────────────────────
        def make_team(name: str, plan: Plan) -> Team:
            team, tcreated = Team.objects.get_or_create(name=name, defaults={"owner": user})
            TeamMember.objects.get_or_create(team=team, user=user, defaults={"role": "owner"})
            if tcreated:
                Subscription.objects.get_or_create(
                    team=team,
                    defaults={
                        "plan": plan,
                        "status": "active",
                        "current_period_start": timezone.now(),
                        "current_period_end": timezone.now() + timedelta(days=30),
                    },
                )
            return team

        team_demo = make_team("VisioX Demo Lab", plan_pro)
        team_edge = make_team("Edge AI Team", plan_starter)
        self.stdout.write("Teams ready.")

        # ── 5. Projects ─────────────────────────────────────────────────
        project_defs = [
            {
                "team": team_demo,
                "name": "Warehouse QC — Line A",
                "task_type": "object_detection",
                "description": "Detect defective products on the assembly line using YOLOv8.",
            },
            {
                "team": team_demo,
                "name": "Retail Shelf Analytics",
                "task_type": "object_detection",
                "description": "Track product placement and out-of-stock events across shelf cameras.",
            },
            {
                "team": team_demo,
                "name": "Medical Imaging — Chest X-ray",
                "task_type": "image_classification",
                "description": "Binary classification of normal vs. abnormal chest radiographs.",
            },
            {
                "team": team_demo,
                "name": "Urban Scene Segmentation",
                "task_type": "semantic_segmentation",
                "description": "Full-pixel labeling for autonomous driving perception stack.",
            },
            {
                "team": team_edge,
                "name": "Jetson Edge Detection",
                "task_type": "object_detection",
                "description": "Optimized YOLOv8n pipeline running at 60 fps on NVIDIA Jetson Nano.",
            },
            {
                "team": team_edge,
                "name": "PCB Defect Inspector",
                "task_type": "instance_segmentation",
                "description": "Mask-level detection of solder bridges, missing components, and scratches.",
            },
        ]
        projects = {}
        for p in project_defs:
            obj, _ = Project.objects.get_or_create(
                name=p["name"],
                defaults={
                    "team": p["team"],
                    "owner": user,
                    "task_type": p["task_type"],
                    "description": p["description"],
                },
            )
            projects[p["name"]] = obj
        self.stdout.write(f"Projects ready ({len(projects)}).")

        # ── 6. Datasets ─────────────────────────────────────────────────
        dataset_defs = [
            {"project": "Warehouse QC — Line A", "name": "Factory Floor v1", "description": "2 840 images captured from conveyor belt camera.", "version": 1},
            {"project": "Warehouse QC — Line A", "name": "Factory Floor v2 — augmented", "description": "v1 + synthetic backgrounds and rotation augmentation.", "version": 2},
            {"project": "Retail Shelf Analytics", "name": "Shelf Images — Store 001", "description": "Morning and afternoon captures from 4 camera angles.", "version": 1},
            {"project": "Medical Imaging — Chest X-ray", "name": "NIH ChestX-ray14 Subset", "description": "3 500 curated samples from the public NIH dataset.", "version": 1},
            {"project": "Urban Scene Segmentation", "name": "Cityscapes Fine Train", "description": "2 975 finely annotated urban driving frames.", "version": 1},
            {"project": "Jetson Edge Detection", "name": "Parking Lot v1", "description": "500 frames from a static outdoor parking camera.", "version": 1},
            {"project": "PCB Defect Inspector", "name": "PCB Microscopy Set A", "description": "1 200 high-res microscopy images of PCB surfaces.", "version": 1},
            {"project": "PCB Defect Inspector", "name": "PCB Microscopy Set B — relabeled", "description": "Set A re-annotated with finer mask boundaries.", "version": 2},
        ]
        datasets = {}
        for d in dataset_defs:
            proj = projects[d["project"]]
            obj, _ = Dataset.objects.get_or_create(
                name=d["name"],
                project=proj,
                defaults={"description": d["description"], "version": d["version"]},
            )
            datasets[d["name"]] = obj
        self.stdout.write(f"Datasets ready ({len(datasets)}).")

        # ── 7. Annotation classes (sample) ──────────────────────────────
        class_defs = [
            {"project": "Warehouse QC — Line A", "name": "defect_scratch", "color": "#EF4444"},
            {"project": "Warehouse QC — Line A", "name": "defect_dent", "color": "#F97316"},
            {"project": "Warehouse QC — Line A", "name": "pass", "color": "#22C55E"},
            {"project": "Retail Shelf Analytics", "name": "product_present", "color": "#3B82F6"},
            {"project": "Retail Shelf Analytics", "name": "out_of_stock", "color": "#EF4444"},
            {"project": "PCB Defect Inspector", "name": "solder_bridge", "color": "#A855F7"},
            {"project": "PCB Defect Inspector", "name": "missing_component", "color": "#EF4444"},
            {"project": "PCB Defect Inspector", "name": "scratch", "color": "#F97316"},
        ]
        for c in class_defs:
            Class.objects.get_or_create(
                project=projects[c["project"]],
                name=c["name"],
                defaults={"color": c["color"]},
            )
        self.stdout.write("Annotation classes ready.")

        # ── 8. Training jobs ────────────────────────────────────────────
        now = timezone.now()
        job_defs = [
            {
                "project": "Warehouse QC — Line A",
                "dataset": "Factory Floor v2 — augmented",
                "arch": "YOLOv8m",
                "name": "YOLOv8m — Warehouse v2",
                "status": "completed",
                "epochs": 100,
                "started_before": 72,
                "duration_h": 3.5,
            },
            {
                "project": "Warehouse QC — Line A",
                "dataset": "Factory Floor v1",
                "arch": "YOLOv8n",
                "name": "YOLOv8n — Baseline",
                "status": "completed",
                "epochs": 80,
                "started_before": 120,
                "duration_h": 1.2,
            },
            {
                "project": "Retail Shelf Analytics",
                "dataset": "Shelf Images — Store 001",
                "arch": "YOLOv8s",
                "name": "YOLOv8s — Shelf Detection",
                "status": "completed",
                "epochs": 100,
                "started_before": 96,
                "duration_h": 2.1,
            },
            {
                "project": "Medical Imaging — Chest X-ray",
                "dataset": "NIH ChestX-ray14 Subset",
                "arch": "ResNet-50",
                "name": "ResNet-50 — ChestX v1",
                "status": "completed",
                "epochs": 90,
                "started_before": 48,
                "duration_h": 4.0,
            },
            {
                "project": "Medical Imaging — Chest X-ray",
                "dataset": "NIH ChestX-ray14 Subset",
                "arch": "ViT-B/16",
                "name": "ViT-B — ChestX (experimental)",
                "status": "failed",
                "epochs": 30,
                "started_before": 24,
                "duration_h": 1.0,
            },
            {
                "project": "Urban Scene Segmentation",
                "dataset": "Cityscapes Fine Train",
                "arch": "DeepLabV3+",
                "name": "DeepLabV3+ — Cityscapes run 1",
                "status": "running",
                "epochs": 80,
                "started_before": 5,
                "duration_h": None,
            },
            {
                "project": "Jetson Edge Detection",
                "dataset": "Parking Lot v1",
                "arch": "YOLOv8n",
                "name": "YOLOv8n — Parking Nano",
                "status": "completed",
                "epochs": 60,
                "started_before": 200,
                "duration_h": 0.8,
            },
            {
                "project": "PCB Defect Inspector",
                "dataset": "PCB Microscopy Set B — relabeled",
                "arch": "Mask R-CNN",
                "name": "Mask R-CNN — PCB Set B",
                "status": "completed",
                "epochs": 100,
                "started_before": 36,
                "duration_h": 6.0,
            },
        ]

        training_jobs = {}
        for jd in job_defs:
            started_at = now - timedelta(hours=jd["started_before"])
            finished_at = (
                started_at + timedelta(hours=jd["duration_h"])
                if jd["duration_h"] and jd["status"] in ("completed", "failed")
                else None
            )
            job, _ = TrainingJob.objects.get_or_create(
                name=jd["name"],
                defaults={
                    "project": projects[jd["project"]],
                    "dataset": datasets.get(jd["dataset"]),
                    "architecture": architectures.get(jd["arch"]),
                    "created_by": user,
                    "status": jd["status"],
                    "hyperparams": {
                        "epochs": jd["epochs"],
                        "lr": round(random.choice([0.001, 0.005, 0.01]), 4),
                        "batch_size": random.choice([8, 16, 32]),
                        "imgsz": 640,
                    },
                    "started_at": started_at,
                    "finished_at": finished_at,
                },
            )
            training_jobs[jd["name"]] = (job, jd)

            # Experiments + metrics only for completed jobs
            if jd["status"] == "completed":
                exp, exp_created = Experiment.objects.get_or_create(
                    job=job,
                    name=f"Run 1 — {jd['arch']}",
                    defaults={"notes": "Auto-generated demo experiment."},
                )
                if exp_created:
                    metrics_to_create = []
                    for epoch in range(1, jd["epochs"] + 1, max(1, jd["epochs"] // 20)):
                        m = _rand_metrics(epoch)
                        metrics_to_create.append(
                            RunMetric(
                                experiment=exp,
                                epoch=epoch,
                                step=epoch * 50,
                                loss=m["loss"],
                                val_loss=m["val_loss"],
                                map50=m["map50"],
                                map75=m["map75"],
                                f1=m["f1"],
                                accuracy=m["accuracy"],
                                recorded_at=started_at + timedelta(minutes=epoch * 2),
                            )
                        )
                    RunMetric.objects.bulk_create(metrics_to_create)

        self.stdout.write(f"Training jobs ready ({len(training_jobs)}).")

        # ── 9. Model registry ───────────────────────────────────────────
        registry_defs = [
            {
                "job": "YOLOv8m — Warehouse v2",
                "name": "warehouse-qc-yolov8m",
                "version": "1.2.0",
                "format": "pytorch",
                "metrics": {"map50": 0.912, "map75": 0.831, "f1": 0.889},
            },
            {
                "job": "ResNet-50 — ChestX v1",
                "name": "chestxray-resnet50",
                "version": "1.0.0",
                "format": "onnx",
                "metrics": {"accuracy": 0.943, "f1": 0.921},
            },
            {
                "job": "YOLOv8n — Parking Nano",
                "name": "parking-yolov8n-edge",
                "version": "2.1.0",
                "format": "tensorrt",
                "metrics": {"map50": 0.879, "f1": 0.854, "latency_ms": 4.2},
            },
            {
                "job": "Mask R-CNN — PCB Set B",
                "name": "pcb-maskrcnn-v2",
                "version": "1.0.0",
                "format": "pytorch",
                "metrics": {"map50": 0.934, "map75": 0.887, "f1": 0.911},
            },
        ]
        registry_entries = {}
        for r in registry_defs:
            job_obj = training_jobs[r["job"]][0]
            entry, _ = ModelRegistry.objects.get_or_create(
                name=r["name"],
                defaults={
                    "training_job": job_obj,
                    "version": r["version"],
                    "format": r["format"],
                    "metrics": r["metrics"],
                    "created_by": user,
                },
            )
            registry_entries[r["name"]] = entry
        self.stdout.write(f"Model registry entries ready ({len(registry_entries)}).")

        # ── 10. Inference endpoints ─────────────────────────────────────
        endpoint_defs = [
            {
                "registry": "warehouse-qc-yolov8m",
                "name": "warehouse-qc-prod",
                "status": "active",
                "rate_limit_rpm": 300,
                "confidence_threshold": 0.45,
            },
            {
                "registry": "chestxray-resnet50",
                "name": "chestxray-staging",
                "status": "inactive",
                "rate_limit_rpm": 60,
                "confidence_threshold": 0.70,
            },
            {
                "registry": "parking-yolov8n-edge",
                "name": "parking-edge-node-01",
                "status": "active",
                "rate_limit_rpm": 600,
                "confidence_threshold": 0.40,
            },
        ]
        for e in endpoint_defs:
            InferenceEndpoint.objects.get_or_create(
                name=e["name"],
                defaults={
                    "registry_entry": registry_entries[e["registry"]],
                    "status": e["status"],
                    "rate_limit_rpm": e["rate_limit_rpm"],
                    "confidence_threshold": e["confidence_threshold"],
                    "endpoint_url": f"https://api.visiox.ai/v1/predict/{e['name']}",
                    "created_by": user,
                },
            )
        self.stdout.write(f"Inference endpoints ready ({len(endpoint_defs)}).")

        # ── 11. Sample media images ─────────────────────────────────────
        total_media = 0
        if not options["skip_media"]:
            n = options["images_per_dataset"]
            self.stdout.write(f"Downloading {n} sample images per dataset…")
            # picsum seed ranges per dataset to get consistent, themed images
            picsum_offsets = {
                "Factory Floor v1":                   1000,
                "Factory Floor v2 — augmented":       1050,
                "Shelf Images — Store 001":            1100,
                "NIH ChestX-ray14 Subset":            1150,
                "Cityscapes Fine Train":               1200,
                "Parking Lot v1":                      1250,
                "PCB Microscopy Set A":                1300,
                "PCB Microscopy Set B — relabeled":    1350,
            }

            from datasets.models import Media  # noqa: PLC0415

            for ds_name, dataset_obj in datasets.items():
                if dataset_obj.media_files.exists():
                    self.stdout.write(f"  {ds_name}: already has media, skipping.")
                    continue

                offset = picsum_offsets.get(ds_name, 2000)
                created_count = 0
                for i in range(n):
                    seed = offset + i
                    url = f"https://picsum.photos/seed/{seed}/640/480"
                    filename = f"IMG_{seed:04d}.jpg"
                    try:
                        with urllib.request.urlopen(url, timeout=10) as resp:
                            img_bytes = resp.read()
                        media = Media(
                            dataset=dataset_obj,
                            type="image",
                            original_filename=filename,
                            width=640,
                            height=480,
                            file_size=len(img_bytes),
                            metadata={"source": "picsum.photos", "seed": seed},
                        )
                        media.file.save(
                            f"demo/{ds_name[:20].replace(' ', '_')}/{filename}",
                            ContentFile(img_bytes),
                            save=False,
                        )
                        media.save()
                        created_count += 1
                        total_media += 1
                    except Exception as exc:
                        self.stdout.write(
                            self.style.WARNING(f"  Could not download {url}: {exc}")
                        )
                self.stdout.write(f"  {ds_name}: {created_count} images added.")
        else:
            self.stdout.write("Skipping media download (--skip-media).")

        # ── Done ────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Login :  {DEMO_EMAIL}")
        self.stdout.write(f"  Password: {DEMO_PASSWORD}")
        self.stdout.write("")
        self.stdout.write("  Teams   : VisioX Demo Lab, Edge AI Team")
        self.stdout.write(f"  Projects: 6  |  Datasets: 8  |  Jobs: 8")
        self.stdout.write(f"  Media   : {total_media} images across all datasets")
        self.stdout.write("  Registry: 4  |  Endpoints: 3 (2 active)")
        self.stdout.write(self.style.SUCCESS("=" * 60))
