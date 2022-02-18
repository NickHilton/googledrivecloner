import pathlib
from setuptools import setup, find_packages


HERE = pathlib.Path(__file__).parent

README = (HERE / "README.md").read_text()

setup(
    name="googledrive_cloner",
    version="1.0.2",
    description="Clone folders in Google Drive",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/NickHilton/googledrivecloner",
    author="Nick Hilton",
    author_email="nicholas.w.hilton@gmail.com",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
    packages=find_packages(exclude=["*tests*"]),
    install_requires=[
        "google-auth-oauthlib>=0.4.3,<0.5",
        "google-auth-oauthlib>=0.4.3,<0.5",
    ],
)
