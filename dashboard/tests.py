from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
from rest_framework import status
from userdetails.models import User
from .models import Booking
from django.conf import settings

class InitiateCallViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='test@example.com', password='password123', phone_number='1234567890')
        self.booking = Booking.objects.create(user=self.user, amount=100, status='confirmed')
        self.url = reverse('initiate-call')

        # Mock ZegoCloud credentials
        self.mock_app_id = 123456789
        self.mock_server_secret = "a" * 32  # 32-character mock secret

        # Patch settings to return mock credentials
        self.patcher_app_id = patch('django.conf.settings.ZEGO_APP_ID', self.mock_app_id)
        self.patcher_server_secret = patch('django.conf.settings.ZEGO_SERVER_SECRET', self.mock_server_secret)
        self.patcher_app_id.start()
        self.patcher_server_secret.start()

    def tearDown(self):
        self.patcher_app_id.stop()
        self.patcher_server_secret.stop()

    @patch('utils.zego_token.generate_token04')
    def test_initiate_call_success(self, mock_generate_token04):
        # Mock the return value of generate_token04
        mock_token_info = MagicMock()
        mock_token_info.token = "mock_kit_token"
        mock_token_info.error_code = 0
        mock_generate_token04.return_value = mock_token_info

        self.client.force_login(self.user)
        response = self.client.post(self.url, {'booking_id': self.booking.id}, content_type='application/json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('kitToken', response.json())
        self.assertIn('room_id', response.json())
        self.assertIn('user_id', response.json())
        self.assertIn('app_id', response.json())
        self.assertIn('expires_in', response.json())
        self.assertEqual(response.json()['kitToken'], "mock_kit_token")
        self.assertEqual(response.json()['room_id'], f"booking_{self.booking.id}")
        self.assertEqual(response.json()['user_id'], str(self.user.id))
        self.assertEqual(response.json()['app_id'], self.mock_app_id)
        self.assertEqual(response.json()['expires_in'], 3600)

        mock_generate_token04.assert_called_once_with(
            app_id=self.mock_app_id,
            user_id=str(self.user.id),
            secret=self.mock_server_secret,
            effective_time_in_seconds=3600,
            payload={'room_id': f'booking_{self.booking.id}', 'privilege': {'1': 1, '2': 1}, 'stream_id_list': []}
        )

    @patch('utils.zego_token.generate_token04')
    def test_initiate_call_missing_booking_id(self, mock_generate_token04):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {}, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertEqual(response.json()['error'], 'booking_id is required')
        mock_generate_token04.assert_not_called()

    @patch('django.conf.settings.ZEGO_APP_ID', None)
    @patch('django.conf.settings.ZEGO_SERVER_SECRET', None)
    def test_initiate_call_missing_zego_credentials(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'booking_id': self.booking.id}, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('error', response.json())
        self.assertEqual(response.json()['error'], 'Video call service not configured')

    @patch('utils.zego_token.generate_token04')
    def test_initiate_call_token_generation_failure(self, mock_generate_token04):
        mock_token_info = MagicMock()
        mock_token_info.token = ""
        mock_token_info.error_code = 1
        mock_token_info.error_message = "Invalid App ID"
        mock_generate_token04.return_value = mock_token_info

        self.client.force_login(self.user)
        response = self.client.post(self.url, {'booking_id': self.booking.id}, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertEqual(response.json()['error'], 'Token generation failed: Invalid App ID')
        mock_generate_token04.assert_called_once()