[![CircleCI](https://circleci.com/gh/NickHilton/googledrivecloner.svg?style=svg)](https://circleci.com/gh/NickHilton/googledrivecloner)


Google Drive Folder Cloner
============




Contents
-----------
1. [Description](#Description)
2. [Install](#Installation)
3. [Usage](#Usage)
4. [Contributing](#contributing)

Description
-------------
A python package for cloning google drive folders, including all subdirectories and files

Installation
-------------

To install from the [pypi release](https://pypi.org/project/googledrive-cloner/)
```bash
pip install googledrive_cloner
```

To install locally
```bash
git clone https://github.com/NickHilton/googledrivecloner.git
```

#### Google Drive Set up
In order for this package to work, any GDrive account you use must be set up with the correct permissions. More detail is given in Google's [documentation](https://cloud.google.com/apis/docs/getting-started)

The following steps should get you set up correctly

1. Create a Google Project - [here](https://console.cloud.google.com/projectcreate?previousPage=%2Fcloud-resource-manager%3ForganizationId%3D0%26project%3D%26folder%3D&organizationId=0)
2. Enable the Google Drive API on your project - [here](https://console.cloud.google.com/apis/library/drive.googleapis.com)
3. Create a service account for authorization as described in the [documentation](https://developers.google.com/identity/protocols/oauth2/service-account)
4. Save the client-secret created during the previous step to your environment and set the environment variable `CLIENT_SECRET_PATH` to point to the file
5. Enable sharing for the folder you wish to copy, and share the folder with the email from the created service account


Usage
-------------
To clone a directory you need to get both the gdrive id of the folder to be copied and the destination folder. You can discover these ids by looking at the url
```
https://drive.google.com/drive/u/0/folders/{FOLDER_ID}
```

The cloner can be used in the following way:
```python
from googledrive_cloner.google_connections import GoogleDriveCloner
googledrivecloner = GoogleDriveCloner()
folder_id_to_copy = 'XXXXXXXX'
destination_folder_id = 'YYYYYYYYY'
new_folder_name = 'lemons'  # Or something else!

googledrivecloner.run(
    base_folder_id=folder_id_to_copy, 
    destination_parent_folder_id=destination_folder_id, 
    new_name=new_folder_name
)
```


Contributing
-------------

All contributions are welcome, feel free to ask a question or propose a change via a Pull Request


#### Running Tests
In the root/src directory

```shell
python -m unittest discover
```

