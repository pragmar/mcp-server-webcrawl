# HTTrack Fixture

## Version Information

**ArchiveBox v0.7.1**

*Cpython Linux Linux-6.14.0-28-generic-x86_64-with-glibc2.39 x86_64*

Configuration

* DEBUG=False
* IN_DOCKER=False
* IN_QEMU=False
* IS_TTY=False
* TZ=UTC
* FS_ATOMIC=True
* FS_REMOTE=False
* FS_USER=1000:1000
* FS_PERMS=644
* SEARCH_BACKEND=ripgrep

## Directory Layout

```
./MCP-SERVER-WEBCRAWL/FIXTURES/HTTRACK
├───example
│   └───example.com
└───pragmar
    └───pragmar.com
        ├───appstat
        │   ├───download
        │   ├───help
        │   └───privacy
        ├───internal
        │   └───this
        │       └───page
        │           └───does
        │               └───not
        │                   └───exist
        ├───mcp-server-webcrawl
        │   └───help
        ├───media
        │   ├───static
        │   │   ├───download
        │   │   ├───fonts
        │   │   ├───images
        │   │   │   ├───appstat
        │   │   │   ├───home
        │   │   │   ├───mcp-server-webcrawl
        │   │   │   ├───moffitor
        │   │   │   └───qbit
        │   │   ├───scripts
        │   │   │   └───js
        │   │   └───styles
        │   │       └───css
        │   └───uploads
        │       └───bin
        ├───moffitor
        │   ├───download
        │   ├───privacy
        │   └───support
        └───qbit
            ├───download
            ├───history
            └───privacy
```
