import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from camera_manager import CameraManager

class TestCameraScan(unittest.TestCase):
    def setUp(self):
        # Clear connected devices before each test
        CameraManager.connected_devices.clear()
        
    @patch('camera_manager.cv2')
    @patch('camera_manager.glob')
    @patch('camera_manager.os')
    def test_auto_reconnect_scan(self, mock_os, mock_glob, mock_cv2):
        """Test that camera automatically scans for new devices when default fails"""
        # Setup mocks
        mock_os.name = 'posix'
        mock_glob.glob.return_value = ['/dev/video0', '/dev/video1']
        
        # Define behavior for VideoCapture
        def video_capture_side_effect(index):
            mock_cap = MagicMock()
            # Simulate video0 failing, video1 succeeding
            # Note: CameraManager converts /dev/videoX to int X for OpenCV
            if index == 0:
                mock_cap.isOpened.return_value = False
            elif index == 1:
                mock_cap.isOpened.return_value = True
            else:
                mock_cap.isOpened.return_value = False
            return mock_cap
            
        mock_cv2.VideoCapture.side_effect = video_capture_side_effect
        
        # Initialize camera with video0
        print("\nTesting auto-reconnect scan...")
        # It should try video0 (fail), then scan and try video0 (fail), then video1 (succeed)
        cam = CameraManager(device='/dev/video0', auto_reconnect=True, debug=True)
        
        # Verify
        self.assertTrue(cam.is_opened())
        self.assertEqual(cam._current_device_path, '/dev/video1')
        self.assertIn('/dev/video1', CameraManager.connected_devices)
        
    @patch('camera_manager.cv2')
    @patch('camera_manager.glob')
    @patch('camera_manager.os')
    def test_multi_camera_conflict(self, mock_os, mock_glob, mock_cv2):
        """Test that second camera doesn't steal first camera's device"""
        print("\nTesting multi-camera conflict...")
        mock_os.name = 'posix'
        mock_glob.glob.return_value = ['/dev/video0', '/dev/video1']
        
        # Define behavior: all devices work initially
        def video_capture_success(index):
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            return mock_cap
            
        mock_cv2.VideoCapture.side_effect = video_capture_success
        
        # 1. Connect Cam 1 to video0
        cam1 = CameraManager(device='/dev/video0', auto_reconnect=True, debug=True)
        self.assertEqual(cam1._current_device_path, '/dev/video0')
        self.assertIn('/dev/video0', CameraManager.connected_devices)
        
        # 2. Connect Cam 2 to video1
        cam2 = CameraManager(device='/dev/video1', auto_reconnect=True, debug=True)
        self.assertEqual(cam2._current_device_path, '/dev/video1')
        self.assertIn('/dev/video1', CameraManager.connected_devices)
        
        # 3. Simulate Cam 2 failing and scanning
        cam2.close() 
        self.assertNotIn('/dev/video1', CameraManager.connected_devices)
        
        # Now we want to verify that if we ask cam2 to scan, it sees video0 is taken
        # We can test _scan_video_devices directly to verify the filtering logic
        devices = cam2._scan_video_devices()
        print(f"Scanned devices: {devices}")
        
        # video0 should be excluded because cam1 is still holding it
        self.assertNotIn('/dev/video0', devices)
        # video1 should be included because we closed cam2
        self.assertIn('/dev/video1', devices)
        
        cam1.close()

if __name__ == '__main__':
    unittest.main()
