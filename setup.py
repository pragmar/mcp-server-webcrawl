import re
from setuptools import setup

# remove centered image that doesn't render for pypi
with open("README.md", "r", encoding="utf-8") as src:
    content = src.read()
modified_content = re.sub(r'<p align="center">.*?</p>', '', content, flags=re.DOTALL)
with open("README_pypi.md", "w", encoding="utf-8") as dest:
    dest.write(modified_content.strip())

# set up configuration in pyproject.toml
setup()