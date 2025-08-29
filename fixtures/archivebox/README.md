# ArchiveBox Fixture

ArchiveBox uses a different usage pattern than the other crawlers. An instance of ArchiveBox represents a collection of URLs, not of a particular website. Therefore, the pattern is different. A "site" becomes an ArchiveBox collection.

You can have just one of these, like a normie. Or you can have multiple instances, selectable from MCP as crawl sites. Just remember, this example here is totally synthetic, and tries to reproduce classic single website crawling in order to run the regular suite of tests. Here are the test domains example.com and pragmar.com, each in their own instances of ArchiveBox.

Like all fixtures data, this has been pruned to keep the overall size reasonable. Large binaries have been eliminated. Keeping .orig and some other duplicate data, however, to keep indexer tests sharp.

## Fixtures Installation Script

```bash
#!/bin/bash

# remove existing installations
rm -rf ~/archivebox-env
rm -rf ~/archivebox-data

# bootstrap from scratch
python3 -m venv ~/archivebox-env
mkdir ~/archivebox-data
source ~/archivebox-env/bin/activate
pip install setuptools
pip install archivebox

# configure for local, minimal archiving
export SAVE_DOM=True
export SAVE_WGET=True
export SAVE_SCREENSHOT=False
export SAVE_MEDIA=False
export SUBMIT_ARCHIVE_DOT_ORG=False
export SAVE_ARCHIVE_DOT_ORG=False
export SAVE_PDF=False
export SAVE_SINGLEFILE=False
export SAVE_READABILITY=False
export SAVE_MERCURY=False
export SAVE_GIT=False

# create example archive
mkdir ~/archivebox-data/example
cd ~/archivebox-data/example
archivebox init
archivebox add < ~/example.urls.txt

# create pragmar archive
mkdir ~/archivebox-data/pragmar
cd ~/archivebox-data/pragmar
archivebox init
archivebox add < ~/pragmar.com.urls.txt

# add admin users
cd ~/archivebox-data/example && archivebox manage createsuperuser
cd ~/archivebox-data/pragmar && archivebox manage createsuperuser
```

## Directory Layout

```
./MCP-SERVER-WEBCRAWL/FIXTURES/ARCHIVEBOX
├───example
│   ├───archive
│   │   └───1756356275.823711
│   │       └───www.example.com
│   ├───logs
│   └───sources
└───pragmar
    ├───archive
    │   ├───1756357684.13
    │   │   └───pragmar.com
    │   │       └───media
    │   │           └───static
    │   │               ├───images
    │   │               │   └───home
    │   │               ├───scripts
    │   │               │   └───js
    │   │               └───styles
    │   │                   └───css
    ├───logs
    └───sources
```
