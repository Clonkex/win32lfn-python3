# win32lfn-python3
This is a modified version of [the original](https://foss.heptapod.net/mercurial/win32lfn) extension that supports Python 3. It's not extensively tested yet but it seems to be working for me on Windows 10 (build 19045) with Mercurial/TortoiseHg 6.5.1 (which appears to bundle Python 3.9.13).

Python 3 appears to have fixed some issues with handling of long paths, so less work required by this extension to fix issues. I've commented out a few lines that appear to be no longer necessary.

Feel free to open issues and PRs and I'll do my best to accomodate.

## Original Readme
Mercurial extension which allows using working copies that contain filenames longer than Windows MAXPATH of 260 characters.

For full documentation see: https://wiki.mercurial-scm.org/Win32LongFileNamesExtension

### Development
To run the tests:

```
set PYTHONPATH=C:\src\hg;c:\src\win32lfn\src
python c:\src\win32lfn\tests\testwin32lfn.py
```

### License
The intent is that this code is under the same license as Mercurial. See https://repo.mercurial-scm.org/hg/file/tip/COPYING

This code is licensed under GPL version 2 or any later version ("GPLv2+"). This means it is completely free for most uses including redistribution.