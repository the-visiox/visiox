from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from annotations.models import Annotation, Class
from datasets.models import Dataset, Media, MediaLabelProfile
from projects.models import Project


class ClassApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='class-owner', password='secret')
        self.project = Project.objects.create(
            owner=self.user,
            name='Class Project',
            task_type='object_detection',
        )
        self.dataset = Dataset.objects.create(project=self.project, name='Dataset')
        self.media = Media.objects.create(
            dataset=self.dataset,
            type='image',
            file='classes/image.jpg',
            original_filename='image.jpg',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_class_list_returns_annotation_count(self):
        annotation_class = Class.objects.create(project=self.project, name='person')
        Annotation.objects.create(
            media=self.media,
            class_label=annotation_class,
            annotator=self.user,
            type='rectangle',
            data={'x': 1, 'y': 1, 'width': 10, 'height': 10},
        )

        response = self.client.get(f'/api/v1/classes/?project={self.project.id}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['annotation_count'], 1)
        self.assertEqual(response.data['results'][0]['index'], 0)

    def test_new_classes_receive_sequential_indexes(self):
        first = Class.objects.create(project=self.project, name='vehicle')
        second = Class.objects.create(project=self.project, name='person')

        self.assertEqual(first.index, 0)
        self.assertEqual(second.index, 1)
        response = self.client.get(f'/api/v1/classes/?project={self.project.id}')
        self.assertEqual([item['id'] for item in response.data['results']], [first.id, second.id])

    def test_reorder_updates_project_class_indexes(self):
        first = Class.objects.create(project=self.project, name='animal')
        second = Class.objects.create(project=self.project, name='person')
        third = Class.objects.create(project=self.project, name='vehicle')

        response = self.client.post('/api/v1/classes/reorder/', {
            'project': self.project.id,
            'class_ids': [third.id, first.id, second.id],
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(item['id'], item['index']) for item in response.data],
            [(third.id, 0), (first.id, 1), (second.id, 2)],
        )

    def test_reorder_rejects_partial_class_list(self):
        first = Class.objects.create(project=self.project, name='animal')
        Class.objects.create(project=self.project, name='person')

        response = self.client.post('/api/v1/classes/reorder/', {
            'project': self.project.id,
            'class_ids': [first.id],
        }, format='json')

        self.assertEqual(response.status_code, 400)

    def test_delete_class_cleans_media_label_profiles(self):
        annotation_class = Class.objects.create(project=self.project, name='person')
        retained_class = Class.objects.create(project=self.project, name='vehicle')
        profile = MediaLabelProfile.objects.create(
            media=self.media,
            labels=[
                {'id': annotation_class.id, 'name': annotation_class.name},
                {'id': retained_class.id, 'name': retained_class.name},
            ],
        )

        response = self.client.delete(f'/api/v1/classes/{annotation_class.id}/')

        self.assertEqual(response.status_code, 204)
        profile.refresh_from_db()
        self.assertEqual(profile.labels, [
            {'id': retained_class.id, 'name': retained_class.name},
        ])
        retained_class.refresh_from_db()
        self.assertEqual(retained_class.index, 0)
