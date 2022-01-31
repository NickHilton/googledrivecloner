from unittest import TestCase
from unittest.mock import patch, Mock, ANY

from google_connections import GoogleDriveCloner, SPREADSHEET_TYPE, FOLDER_TYPE
from tests.mock_service import MockService, File


class GoogleDriveClonerTests(TestCase):
    def setUp(self) -> None:
        self.service = MockService()
        self.gdrive = GoogleDriveCloner(self.service)

    def cache_file_info(self):
        """
        Cache file store from mock_service to the GDrive client,
        mocking out the call to GoogleDriveCloner.get_all_file_info
        in the GoogleDriveCloner.__init__
        """
        self.gdrive.file_info = {
            k: self.service._get(k, single_parent=True) for k in self.service.files
        }

    def test__clone_file(self):
        """Test google_connections.GoogleDriveCloner._clone_file"""
        current_file = File(file_id="file1", name="file", parents=["parent1"])
        self.service._add_file(current_file)
        actual = self.gdrive._clone_file(file_id="file1")
        expected = {"id": ANY}
        self.assertEqual(actual, expected)

        # Test file cloned with parent
        self.assertEqual(self.service.files[actual["id"]], current_file)

    def test__get_file_info_one_page(self):
        """Test google_connections.GoogleDriveCloner._get_file_info_one_page"""

        self.service._add_file(File("1", "file1", ["2"]))
        self.service._add_file(File("11", "file11", ["12"]))

        actual = self.gdrive._get_file_info_one_page()
        expected_return_dict = {
            "1": {"parent": "2", "name": "file1", "mimeType": "mime"},
            "11": {"parent": "12", "name": "file11", "mimeType": "mime"},
        }
        expected = (
            expected_return_dict,
            None,
        )
        self.assertEqual(actual, expected)

        # Test nextPageToken returned
        self.service.next_tokens = ["nextToken"]
        actual = self.gdrive._get_file_info_one_page(
            page_token="pageToken", query="query"
        )
        expected = (
            expected_return_dict,
            "nextToken",
        )
        self.assertEqual(actual, expected)

        # Test passed kwargs are sent to service.list()
        call_args = self.service.list_mock.call_args_list[-1]
        self.assertEqual(call_args[1]["pageToken"], "pageToken")
        self.assertEqual(call_args[1]["q"], "query")

        # Test empty response
        self.service.files = dict()
        self.service.list_items = iter(
            [
                {
                    "files": [],
                },
            ]
        )
        actual = self.gdrive._get_file_info_one_page()
        expected = (dict(), None)

        self.assertEqual(actual, expected)

    @patch("google_connections.GoogleDriveCloner._get_file_info_one_page")
    def test__get_all_file_info(self, mock_page):
        """Test google_connections.GoogleDriveCloner._get_all_file_info"""
        mock_page.side_effect = [
            ({"1": {"attr": "2"}, "11": {"attr": "12"}}, "token"),
            ({"21": {"attr": "22"}, "31": {"attr": "32"}}, None),
        ]
        actual = self.gdrive._get_all_file_info()
        expected = {
            "1": {"attr": "2"},
            "11": {"attr": "12"},
            "21": {"attr": "22"},
            "31": {"attr": "32"},
        }
        self.assertEqual(actual, expected)

    def test__delete_file(self):
        """Test google_connections.GoogleDriveCloner._delete_file"""
        self.service._add_file(File("1", "file1"))
        actual = self.gdrive._delete_file(file_id="1")
        expected = {"id": "1"}
        self.assertEqual(actual, expected)
        self.assertEqual(self.service.files, dict())

    @patch("google_connections.GoogleDriveCloner._get_file_info_one_page")
    def test__cleanup_files(self, mock_page):
        """Test google_connections.GoogleDriveCloner._cleanup_files"""
        parent = self.service._add_file(File("1"))
        destination_parent = self.service._add_file(File("2"))
        old_file = self.service._add_file(File("3", name="test_file", parents=["1"]))
        # Cache state of files before anything was run
        self.cache_file_info()

        # Test nothing happens when new file created on its own
        new_file = self.service._add_file(File("4", name="test_file", parents=["2"]))

        def _mock_page_for_files(files):
            return (
                {file_id: self.service._get(file_id) for file_id in files},
                None,
            )

        def _mock_page_side_effect(original_files, destination_files):
            return [
                _mock_page_for_files(original_files),
                _mock_page_for_files(destination_files),
            ]

        # Current then destination files
        mock_page.side_effect = _mock_page_side_effect(["3"], ["4"])
        self.gdrive._cleanup_files(
            parent_id=parent.id, destination_parent_id=destination_parent.id
        )

        # Test nothing deleted
        self.assertEqual(list(sorted(self.service.files)), ["1", "2", "3", "4"])
        # Test original file and new files are unchanged
        self.assertEqual(self.service.files[old_file.id], old_file)
        self.assertEqual(self.service.files[new_file.id], new_file)

        # Scenario: Copy was created and not moved, also an existing copy was in the
        # original dir
        del self.service.files[new_file.id]
        self.service._add_file(
            File("4", name="Copy of another file BAD", parents=["1"])
        )
        self.service._add_file(
            File("5", name="Copy of another file GOOD", parents=["1"])
        )
        # Cache state of files before anything was run

        self.cache_file_info()

        # Bad copies happened
        self.service._add_file(File("6", name="Copy of test_file", parents=["1"]))
        self.service._add_file(
            File("7", name="Copy of Copy of another file BAD", parents=["1"])
        )

        # But a good copy did happen
        new_successfully_copied_file = self.service._add_file(
            File("8", name="Copy of another file GOOD", parents=["2"])
        )

        mock_page.side_effect = _mock_page_side_effect(["3", "4", "5", "6", "7"], ["8"])

        self.gdrive._cleanup_files(
            parent_id=parent.id, destination_parent_id=destination_parent.id
        )
        # Nothing should have been deleted
        self.assertEqual(
            list(sorted(self.service.files)), ["1", "2", "3", "4", "5", "6", "7", "8"]
        )
        # ids = 6,7 should have been moved to new parent
        for original, new in [("3", "6"), ("4", "7")]:
            new_file_moved = self.service.files[new]
            original_file = self.service.files[original]
            expected_file = File(new, original_file.name, parents=["2"])
            self.assertEqual(new_file_moved, expected_file)

        # id = 8 should have been left there
        self.assertEqual(
            new_successfully_copied_file,
            self.service.files[new_successfully_copied_file.id],
        )

        # Scenario: An exisiting copy was in destination,
        # but copy happened to current parent, want the auto generated copy moved over
        for file in ["4", "5", "6", "7", "8"]:
            del self.service.files[file]

        existing_copy_of_file = self.service._add_file(
            File("4", name="test_file", parents=["2"])
        )

        # Cache state of files before anything was run

        self.cache_file_info()

        self.service._add_file(File("5", name="Copy of test_file", parents=["1"]))

        mock_page.side_effect = _mock_page_side_effect(["3", "5"], ["4"])
        self.gdrive._cleanup_files(
            parent_id=parent.id, destination_parent_id=destination_parent.id
        )
        # Id = 4 should have been deleted
        self.assertEqual(list(sorted(self.service.files)), ["1", "2", "3", "5"])
        self.assertEqual(self.service.files["5"], existing_copy_of_file)

    def test__get_one_file_info(self):
        """Test google_connections.GoogleDriveCloner._get_one_file_info"""
        self.service._add_file(File("1", "test file", parents=["2"]))
        actual = self.gdrive._get_one_file_info("1")
        expected = {
            "id": "1",
            "name": "test file",
            "parents": ["2"],
            "mimeType": "mime",
        }
        self.assertEqual(actual, expected)
        self.service.get_mock.assert_called_with(
            fileId="1", fields="id,mimeType,name,parents"
        )

        # Test getting only some fields
        self.gdrive._get_one_file_info("1", fields=["name"])
        self.service.get_mock.assert_called_with(fileId="1", fields="name")

    def test_move_file(self):
        """Test google_connections.GoogleDriveCloner.move_file"""
        # Test standard moving of file
        self.service._add_file(File("1", name="test file", parents=["2"]))
        self.gdrive.move_file(file_id="1", destination_parent_id="3")
        actual = self.service.files["1"]
        expected_file = File("1", name="test file", parents=["3"])
        self.assertEqual(actual, expected_file)

        # Test specific parent removed
        self.service._add_file(File("11", name="another test file", parents=["2", "3"]))
        self.gdrive.move_file(
            file_id="11",
            destination_parent_id="4",
            current_parent_id="2",
            name="another test file",
            mime_type="mime",
        )
        actual = self.service.files["11"]
        expected_file = File("11", name="another test file", parents=["3", "4"])
        self.assertEqual(actual, expected_file)

    @patch("google_connections.time.sleep")
    @patch("google_connections.GoogleDriveCloner._cleanup_files")
    def test_copy_file(self, mock_cleanup, mock_sleep):
        """Test google_connections.GoogleDriveCloner.copy_file"""
        self.service._add_file(File("1", "test file", parents=["2"]))
        self.cache_file_info()
        copied_id = self.gdrive.copy_file("1", "3")
        new_file = self.service.files[copied_id]
        expected_file = File("1", "test file", parents=["3"])
        self.assertEqual(expected_file, new_file)
        # Shouldn't sleep for a non spreadsheet

        # Test a spreadsheet sleeps
        self.service._add_file(
            File("1", "test file", parents=["2"], mimeType=SPREADSHEET_TYPE)
        )
        self.cache_file_info()
        self.gdrive.copy_file("1", "3")
        # Should have slept
        mock_sleep.assert_called_once()
        # One cleanup per call
        self.assertEqual(mock_cleanup.call_count, 2)

        # Test copied files updated
        expected = {"1"}
        actual = self.gdrive.copied_files
        self.assertEqual(actual, expected)

    def test_create_folder(self):
        """Test google_connections.GoogleDriveCloner.create_folder"""
        created_id = self.gdrive.create_folder(
            destination_parent_id="1", new_name="test folder"
        )
        expected = File(
            file_id="2", parents=["1"], name="test folder", mimeType=FOLDER_TYPE
        )
        self.assertEqual(expected, self.service.files[created_id])

    @patch("google_connections.time.sleep")
    @patch("google_connections.GoogleDriveCloner._cleanup_files")
    def test_copy_item(self, mock_cleanup, mock_sleep):
        """Test google_connections.GoogleDriveCloner.copy_item"""
        # Test copying a regular file
        self.service._add_file(File(file_id="1", name="test name", parents=["2"]))
        self.cache_file_info()
        copied_id = self.gdrive.copy_item("1", "3")
        expected = File(file_id="2", parents=["3"], name="test name")
        self.assertEqual(expected, self.service.files[copied_id])

        # If we try and copy again, shouldn't execute
        actual = self.gdrive.copy_item("1", "3")
        self.assertIsNone(actual)
        # Remove copied file
        del self.service.files[copied_id]

        # Test copying a complex structure including folders and sub folders
        # ROOT -> 2 -> [1, 4, 5 -> [6]]
        self.gdrive.copied_files = set()
        self.gdrive.folders_copied = list()
        self.service._add_file(
            File(file_id="4", name="another test name", parents=["2"])
        )
        self.service._add_file(
            File(file_id="2", name="test folder", mimeType=FOLDER_TYPE)
        )
        self.service._add_file(
            File(
                file_id="5",
                name="another test folder",
                mimeType=FOLDER_TYPE,
                parents=["2"],
            )
        )
        self.service._add_file(
            File(file_id="7", name="destination folder", mimeType=FOLDER_TYPE)
        )
        self.service._add_file(File(file_id="6", name="a sub-dir file", parents=["5"]))
        self.cache_file_info()

        self.gdrive.copy_item("2", "7")
        # Check for path Root -> 7 -> 2C -> [1C, 4C, 5C -> [6C]]
        # 2C is a copy of 2, 1C is a copy of 1 etc.

        # Get copied file ids from originals
        ref = dict()
        for file_id in ["1", "2", "4", "5", "6"]:
            file = self.service.files[file_id]
            new_id = next(
                new_file_id
                for new_file_id, new_file in self.service.files.items()
                if new_file.name == file.name and new_file_id != file_id
            )
            ref[file_id] = new_id

        expected_file_structure = [
            "7",
            [
                [
                    ref["2"],
                    list(
                        sorted(
                            [ref["1"], ref["4"], [ref["5"], [ref["6"]]]],
                            key=lambda i: str(i),
                        )
                    ),
                ]
            ],
        ]
        root_children = self.service.file_structure.print()[1]
        self.assertIn(expected_file_structure, root_children)

    @patch("google_connections.GoogleDriveCloner._cleanup_files")
    @patch("google_connections.time.sleep")
    def test_run_cleanup(self, mock_sleep, mock_cleanup):
        """Test google_connections.GoogleDriveCloner.create_folder"""
        created_id = self.gdrive.create_folder(
            destination_parent_id="1", new_name="test folder"
        )
        self.cache_file_info()
        # Copy folder
        copied_id = self.gdrive.copy_item(created_id, "2")
        self.gdrive.run_cleanup()
        mock_cleanup.assert_called_once_with(created_id, copied_id)
