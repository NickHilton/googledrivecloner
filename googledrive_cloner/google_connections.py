import logging
import time
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient import discovery

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_TYPE = "application/vnd.google-apps.folder"
SPREADSHEET_TYPE = "application/vnd.google-apps.spreadsheet"
CLIENT_SECRET_PATH = os.environ.get("CLIENT_SECRET_PATH", "../client_secret.json")

MIME_TYPE_ORDER = {FOLDER_TYPE: 1, SPREADSHEET_TYPE: 0}

DEFAULT_NUM_RETRIES = "3"
NUM_RETRIES = int(os.environ.get("NUM_RETRIES", DEFAULT_NUM_RETRIES))

CLEANUP_SLEEP = 45
SPREADSHEET_SLEEP = 30
COPY_SLEEP = 1

class GoogleDriveCloner:
    def __init__(self, service: discovery.Resource = None):
        """
        Build GDrive client, with auth and cache current state of file system
        :param service: (discovery.Resource) an already authenticated service account
            files client
        """
        if not service:
            credentials = service_account.Credentials.from_service_account_file(
                CLIENT_SECRET_PATH, scopes=SCOPES
            )
            service = discovery.build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            ).files()
        self.service = service

        # Cache all current file info
        self.file_info = self._get_all_file_info()

        # Init stores of files and folders already copied
        self.copied_files = set()
        self.folders_copied = list()

    def _get_all_file_info(self) -> Dict[str, Dict[str, str]]:
        """
        Gets state of current file system the client has access to

        :return: (dict) of {file_id: {field:value}
        """
        file_id_to_info = defaultdict(dict)
        init = True
        next_token = None
        while init or next_token:
            init = False
            next_page_info, next_token = self._get_file_info_one_page(
                page_token=next_token
            )
            for file_id, info in next_page_info.items():
                file_id_to_info[file_id] = info

        return dict(file_id_to_info)

    def _get_file_info_one_page(
        self, page_token: Optional[str] = None, query: Optional[str] = None
    ) -> Tuple[Dict[str, Dict[str, str]], Optional[str]]:
        """
        Gets file_id to info for one page of files in the drive

        :param page_token: (str or None) nextToken to pass to gdrive API
        :param query: (str or None) query to search for
        :return: (dict(str, dict(str,str), str) of {file_id : {field: value}}, nextToken
        """
        fields = ["id", "kind", "name", "mimeType", "parents"]
        kwargs = {
            "pageSize": 1000,
            "fields": f"files({','.join(fields)}), nextPageToken",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        if query:
            kwargs["q"] = query

        resp = self.service.list(**kwargs).execute()

        file_data = resp["files"]
        file_id_to_info = defaultdict(dict)

        for file in file_data:
            file_id = file.pop("id")
            for k, v in file.items():
                if k == "parents":
                    file_id_to_info[file_id]["parent"] = v[0]
                else:
                    file_id_to_info[file_id][k] = v

        return dict(file_id_to_info), resp.get("nextPageToken")

    def _clone_file(self, file_id: str) -> dict:
        """
        Clone a file in gDrive

        :param file_id: (str) to clone
        :return: (dict) response from gdrive service
        """
        cloned = self.service.copy(**{"fileId": file_id}).execute(
            num_retries=NUM_RETRIES
        )
        return cloned

    def _delete_file(self, file_id: str) -> dict:
        """
        Delete a file in gDrive

        :param file_id: (str) fileId to delete
        :return: (dict) response from gdrive service
        """
        deleted = self.service.delete(**{"fileId": file_id}).execute(
            num_retries=NUM_RETRIES
        )
        return deleted

    def _cleanup_files(self, parent_id: str, destination_parent_id: str):
        """
        Clean up files (potentially recursively) copied by the gdrive API

        :param parent_id: (str) original parent folder id
        :param destination_parent_id: (str) destination folder
        :return: (None) Cleans up files in drive
        """
        current_query = f"'{parent_id}' in parents"
        files_in_current, _ = self._get_file_info_one_page(query=current_query)

        destination_query = f"'{destination_parent_id}' in parents"
        files_in_destination, _ = self._get_file_info_one_page(query=destination_query)
        destination_file_name_to_id = {
            v["name"]: k for k, v in files_in_destination.items()
        }

        for current_file_id, file_info in files_in_current.items():
            clean_name = file_info["name"]
            prefix = "Copy of "
            is_copy = clean_name.startswith(prefix)
            if is_copy:
                logger.info(f'cleaning up {file_info["name"]}')

            # It was not there at the start of this so was just created
            if current_file_id not in self.file_info:
                if is_copy:
                    clean_name = clean_name[len(prefix) :]

                # If a copy of it was already in the destination, delete that,
                # we want the auto gen one
                if clean_name in destination_file_name_to_id:
                    id_to_delete = destination_file_name_to_id[clean_name]

                    # It's already moved, gdrive is being slow to sync so showing files
                    # in multiple places
                    if id_to_delete == current_file_id:
                        logger.info(f"file {clean_name} has already moved")
                        continue

                    # Otherwise, delete the already copied file
                    self._delete_file(id_to_delete)

                # Move auto gen file to the destination
                self.move_file(
                    current_file_id,
                    destination_parent_id=destination_parent_id,
                    current_parent_id=parent_id,
                    name=clean_name,
                    mime_type=file_info["mimeType"],
                )

    def _get_one_file_info(
        self, file_id: str, fields: Optional[List[str]] = None
    ) -> dict:
        """
        Get file info for a file_id

        :param file_id: (str) id of file to get info for
        :param fields: (list(str) or None) fields to fetch
        :return: (dict) of one file's info
        """
        fields = fields or ["id", "mimeType", "name", "parents"]
        resp = self.service.get(fileId=file_id, fields=",".join(fields)).execute()
        return resp

    def move_file(
        self,
        file_id: str,
        destination_parent_id: str,
        current_parent_id: Optional[str] = None,
        name: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> str:
        """
        Copy file in Gdrive to destination_parent_id

        :param file_id: (str) id of file to copy
        :param destination_parent_id: (str) id of folder to copy to
        :param current_parent_id: (str or None) of current parent folder if known
            - prevents call to API to fetch if not needed
        :param name: (str or None) of file name
        :param mime_type: (str or None) of file mime_type
        :return: (str) id of copied file
        """
        # If all were not passed we need to fetch them
        if not (current_parent_id and name and mime_type):
            file_info = self._get_one_file_info(file_id)
            current_parent_id = file_info["parents"][0]
            name = file_info["name"]
            mime_type = file_info["mimeType"]

        kwargs = {
            "fileId": file_id,
            "addParents": destination_parent_id,
            "removeParents": current_parent_id,
            "body": {"name": name},
        }

        resp = self.service.update(**kwargs).execute(num_retries=NUM_RETRIES)

        return resp["id"]

    def copy_file(self, file_id: str, destination_parent_id: str) -> str:
        """
        Copy file in Gdrive to destination_parent_id

        :param file_id: (str) id of file to copy
        :param destination_parent_id: (str) id of folder to copy to
        :return: (str) id of copied file
        """
        cloned = self._clone_file(file_id)
        current = self.file_info[file_id]

        moved = self.move_file(
            file_id=cloned["id"],
            destination_parent_id=destination_parent_id,
            current_parent_id=current["parent"],
            name=current["name"],
            mime_type=current["mimeType"],
        )
        # If we just moved a spreadsheet. Pause for gDrive to catch up
        if current["mimeType"] == SPREADSHEET_TYPE:
            time.sleep(SPREADSHEET_SLEEP)

        # Add file to copied files store
        self.copied_files.add(file_id)

        self._cleanup_files(
            parent_id=current["parent"], destination_parent_id=destination_parent_id
        )
        return moved

    def create_folder(self, destination_parent_id: str, new_name: str) -> str:
        """
        Create an empty folder in gdrive

        :param destination_parent_id: (str) id of containing folder
        :param new_name: (str) name of created folder
        :return: (str) id of created folder in gdrive
        """

        resp = self.service.create(
            body={
                "name": new_name,
                "mimeType": FOLDER_TYPE,
                "parents": [destination_parent_id],
            }
        ).execute(num_retries=NUM_RETRIES)

        return resp["id"]

    def copy_item(
        self, item_id: str, destination_parent_id: str, new_name: Optional[str] = None
    ):
        """
        Copy an item (folder or other type) in GDrive
            If folder will recursively copy all descendant files

        :param item_id: (str) item id to copy
        :param destination_parent_id: (str) id of folder to copy item to
        :param new_name: (str or None) name of file
        :return: (str) id of new copied item
        """
        # Let GDrive catch up
        time.sleep(COPY_SLEEP)

        item_info = self.file_info[item_id]
        name = item_info["name"]
        mimeType = item_info["mimeType"]

        # Already copied the file so skip
        if item_id in self.copied_files:
            return None

        # If item is a folder then create a new folder and
        # copy all child components into
        if mimeType == FOLDER_TYPE:

            created_folder_id = self.create_folder(
                destination_parent_id=destination_parent_id,
                new_name=new_name or item_info["name"],
            )

            # Iterate through our files and if they are a child of the copied item,
            # also copy them over
            # First though order them by the priority of copying
            child_files_to_copy = defaultdict(list)
            for file_id, file in self.file_info.items():
                if file.get("parent") == item_id:
                    mimeType = file["mimeType"]
                    priority = MIME_TYPE_ORDER.get(mimeType, -1)
                    child_files_to_copy[priority].append((file_id, created_folder_id))

            priorities = list(sorted(child_files_to_copy))[::-1]
            for priority in priorities:
                for file_id, created_folder_id in child_files_to_copy[priority]:
                    self.copy_item(file_id, created_folder_id)

            self.copied_files.add(item_id)
            self.folders_copied.append((item_id, created_folder_id))

            return created_folder_id
        else:
            return self.copy_file(
                file_id=item_id, destination_parent_id=destination_parent_id
            )

    def run_cleanup(self):
        """
        Clean up all files in the folders which have been copied

        :return: (None) Runs clean up of files
        """
        for parent, destination in self.folders_copied:
            self._cleanup_files(parent, destination)

    def run(
        self,
        base_folder_id: str,
        destination_parent_folder_id: str,
        new_name: Optional[str] = None,
    ):
        """
        Run the main functionality, copying a folder to a new parent

        :param base_folder_id: (str) folder id to copy
        :param destination_parent_folder_id: (str) id of folder to copy base folder to
        :param new_name: (str or None) name of file
        :return: (str) id of new copied folder
        """

        failed = False
        exception = None
        result = None
        try:
            result = self.copy_item(
                item_id=base_folder_id,
                destination_parent_id=destination_parent_folder_id,
                new_name=new_name,
            )
        except Exception as e:
            exception = e
            failed = True
            logger.info("failed", e)

        logger.info("waiting before cleanup for gDrive sync")
        time.sleep(CLEANUP_SLEEP)
        self.run_cleanup()

        if failed:
            raise exception

        return result

