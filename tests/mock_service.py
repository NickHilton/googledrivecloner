import copy
from typing import Dict, List, Optional, Set, Union
from unittest.mock import Mock


from uuid import uuid4


class File:
    """
    Mock File class representing a GoogleDrive File with basic information
    file_id, name, parents (list of parent ids), mimeType
    """

    def __init__(
        self,
        file_id: str,
        name: str = "",
        parents: List[str] = None,
        mimeType: str = "mime",
    ):
        self.id = file_id
        self.name = name
        self.parents = parents or list()
        self.mimeType = mimeType

    def __eq__(self, other: "File") -> bool:
        return (
            self.name == other.name
            and self.parents == other.parents
            and self.mimeType == other.mimeType
        )

    def __repr__(self) -> str:
        return f"mimeType: {self.mimeType}, name:{self.name}, parents: {self.parents}"

    def copy(self, new_id: str) -> "File":
        """
        Make a copy of this file, under a different id
        :param new_id: (str) of new file id
        :return: (File)
        """
        return File(
            file_id=new_id,
            name=self.name,
            parents=copy.copy(self.parents),
            mimeType=self.mimeType,
        )


class Node:
    """Node in the file directory tree"""

    def __init__(self, file_id: str, parent_node: "Node" = None):
        self.file_id = file_id
        self.parent_node = parent_node
        self.children: Set["Node"] = set()


class Tree:
    """Mocked version of a file directory tree"""

    def __init__(self):
        self.root = Node(file_id="root")
        self.nodes = {"root": self.root}

    def link_parent(self, child_node: Node, parent_id: str) -> None:
        """
        Link child node to parent id, creating a parent if it doesn't exist
        :param child_node: (Node)
        :param parent_id: (str)
        :return: (None) updates tree
        """
        parent_id = parent_id or "root"
        # Create parent if it doesn't exist
        if parent_id not in self.nodes:
            self.nodes[parent_id] = Node(file_id=parent_id)

        # Add parent to child
        self.nodes[child_node.file_id].parent_node = self.nodes[parent_id]
        # Add child to parent's children
        self.nodes[parent_id].children.add(self.nodes[child_node.file_id])

    def add(self, file_id: str, parent_id: str) -> None:
        """
        Add a Node with a given file_id (if it doesn't exist) and link to parent_id
        :param file_id: (str)
        :param parent_id: (str)
        :return: (None)
        """
        if file_id not in self.nodes:
            self.nodes[file_id] = Node(file_id=file_id)
        child_node = self.nodes[file_id]
        self.link_parent(child_node, parent_id)

    def print_node(self, node: Node) -> list:
        """
        Get a list representation of the node,
        [node.file_id, [children nodes]]
        :param node: (Node)
        :return: (list)
        """
        children = list()
        for child_node in node.children:
            if not child_node.children:
                children.append(child_node.file_id)
            else:
                children.append(self.print_node(child_node))
        return [node.file_id, list(sorted(children, key=lambda child: str(child)))]

    def print(self) -> list:
        """
        Get a list representation of the whole file structure,
        starting with the root node
        :return: (list)
        """
        return self.print_node(self.nodes["root"])


def return_execute(func: callable):
    """
    Transform function to return a Mock so that the function only runs when `execute`
    is called
    i.e.
    @return_execute
    def foo():
     return 1

    foo().execute() -> 1

    :param func: (callable) to decorate
    :return: (callable) which returns a Mock with an `execute` method
    """

    def inner(*a, **k):
        mock = Mock()
        mock.execute.side_effect = lambda *args, **kwargs: func(*a, **k)
        return mock

    return inner


class MockService:
    def __init__(
        self,
    ):
        """
        Mock Google Drive Files Service
        """
        self.list_mock = Mock()
        self.get_mock = Mock()
        self.next_tokens = list()

        # file to parent
        self.files: Dict[str, File] = dict()

    @return_execute
    def create(self, body, *a, **k) -> dict:
        file_id = str(uuid4())
        new_file = File(
            file_id=file_id,
            parents=body["parents"],
            mimeType=body["mimeType"],
            name=body["name"],
        )
        self.files[file_id] = new_file
        return {"id": file_id}

    @return_execute
    def copy(self, fileId: str) -> dict:
        old_file = self.files[fileId]
        new_id = str(uuid4())
        new_file = old_file.copy(new_id)
        new_file.id = new_id
        self.files[new_id] = new_file
        return {"id": new_id}

    @return_execute
    def delete(self, fileId: str) -> dict:
        del self.files[fileId]
        return {"id": fileId}

    @return_execute
    def update(self, **kwargs):
        file_id = kwargs["fileId"]
        file = self.files[file_id]
        file.parents.remove(kwargs["removeParents"])

        file.parents.append(kwargs["addParents"])

        file.name = kwargs["body"]["name"]
        self.files[file_id] = file
        return {"id": file_id}

    def _get(
        self,
        fileId: str,
        fields: str = "mimeType,name,parents",
        single_parent: bool = False,
    ) -> Dict[str, Optional[Union[str, list]]]:
        """
        Get a representation of the file as a dict,
        returning any extra fields with dummy values
        Also cleans parent field if requested to only return an id, not list
        :param fileId: (str)
        :param fields: (str) to get, comma separated
        :param single_parent: (bool) only return the single parent id
        :return: (dict)
        """
        file = self.files[fileId]
        resp: Dict[str, Optional[Union[str, list]]] = {
            **{field: f"{field}_value" for field in fields.split(",")},
            **{
                "id": fileId,
                "parents": file.parents,
                "mimeType": file.mimeType,
                "name": file.name,
            },
        }
        if single_parent:
            if file.parents:
                resp["parent"] = file.parents[0]
            else:
                resp["parent"] = None
            del resp["parents"]
        return resp

    @return_execute
    def get(self, fileId: str, fields: str = "mimeType,name,parents", *args, **kwargs):
        """Also logs to the Mock -> self.get_mock for analysis of passed kwargs"""
        self.get_mock(fileId=fileId, fields=fields, *args, **kwargs)
        return self._get(fileId, fields)

    @return_execute
    def list(self, *args, **kwargs):
        """Also logs to the Mock -> self.list_mock for analysis of passed kwargs"""
        self.list_mock(*args, **kwargs)
        resp = {
            "files": [
                self._get(file_id, fields="name,parents,mimeType")
                for file_id in self.files
            ]
        }
        if self.next_tokens:
            resp["nextPageToken"] = self.next_tokens.pop()
        return resp

    def _add_file(self, file: File) -> File:
        """
        Add a file to the file store
        :param file: (File) to add
        :return: (File)
        """
        self.files[file.id] = file
        return file

    @property
    def file_structure(self) -> Tree:
        """
        Get a tree representation of the current file structure
        :return: (Tree)
        """
        tree = Tree()
        for file_id in sorted(self.files):
            file = self.files[file_id]
            parent_id = file.parents[0] if file.parents else None
            tree.add(file_id, parent_id)

        return tree
