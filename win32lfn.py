'''Allow manipulating long file names

''Author: Aaron Cohen <aaron@assonance.org>''

=== Overview ===

Allows creating working copy files whose path is longer than 260 characters on
 Windows (up to ~32768 characters).

Caveats:

 - Some filesystems may have their own pathname restrictions, such as some FAT
   filesystems. Use NTFS or a newer FAT.

 - cmd.exe and powershell have trouble manipulating long pathnames (del, move,
   rename will all fail).

 - Many legacy Windows programs will have difficulty opening files with long
   pathnames, though most java and 64-bit programs will work fine.

 - explorer.exe may have trouble manipulating directories with long paths, with
   dialogs like, "The source file name(s) are larger than is supported
   by the file system. Try moving to a location which has a shorter path name."
   To address this, use a tool other than explorer.exe or delete the affected
   files using :hg:`lfn --clean`.

 - Things get more complicated if the root of your repository is more than 244
   characters long, including directory separators.

     - There is no way in Windows to "cd" into a directory that long. As a
       result, to use hg with the repo, you will have to use
       :hg:`-R` or :hg:`--repository`.

     - When Mercurial first starts up, it will not be able to find the
       ".hg" directory in such a repository until this extension is loaded.
       This implies that this extension must be configured in either the
       system-wide or user hgrc or mercurial.ini, not the per-repository
       ".hg/hgrc".

=== Configuration ===

Enable the extension in the configuration file (mercurial.ini)::

    [extensions]
    win32lfn = C:\path\to\extension\win32lfn.py
'''

import builtins, os, errno

from mercurial import util, cmdutil, registrar
from mercurial.i18n import _

_uncprefix = "\\\\?\\"

_deviceprefix = "\\\\.\\"

_maxpath = 260

_WINDOWS_RESERVED_NAMES = ({'CON','PRN','AUX','NUL','COM1','COM2','COM3',
    'COM4','COM5','COM6','COM7','COM8','COM9','LPT1','LPT2','LPT3','LPT4',
    'LPT5','LPT6','LPT7','LPT8','LPT9'})

# Windows directory paths are limited to MAX_PATH - the dos file size (8.3)
_maxdirpath = 248

_cwd = None

def wrapabspath(abspath):
    '''Wrap os.path.abspath with a version that handles long UNC paths.
    The original version handles UNC format ok, but breaks if the path is
    longer than MAX_PATH (it returns a relative path instead of an absolute
    one).
    In other words, with the original version:
>>> os.path.abspath(30 * "123456789\\")
30 * "123456789\\"'''

    # If this calls any wrapped functions, it might recurse into uncabspath
    def lfnabspath(path):
        result = os.path.normpath(path)
        if not os.path.isabs(result):
            if result == ".":
                return os.getcwd()
            elif result == "..":
                result = os.path.split(os.getcwd())[0]
            else:
                result = os.path.join(os.getcwd(), result)
        return result

    return lfnabspath

# UNC filenames require different normalization than mercurial and python want
def uncabspath(path):
    # We can only handle string arguments (the same as python), but we need to 
    # be sure to use the same exception type as python would in our overrides.
    # For instance, the mercurial patcher tries to open patch chunks, and expects
    # a TypeError so that it can magically handle both pathes and already opened chunks
    path = bytestostring(path)
    if not isinstance(path, str):
        raise TypeError("%s is not a string (%s)" % (path, type(path)))
    if not path.startswith(_uncprefix) and not path.startswith(_deviceprefix) and not path.upper() in _WINDOWS_RESERVED_NAMES:
        path = os.path.abspath(path)
        # path may now be UNC after abspath (which is our wrapped abspath here)
        if not path.startswith(_uncprefix):
            if path.startswith("\\\\"):
                # path is a UNC network path (ie, \\server\share\path)
                # Believe it or not, the literal UNC here is part of
                # Microsoft's API
                path = _uncprefix + "UNC" + path[1:]
            else:
                path = _uncprefix + path
    #print "Path: %s\n" % path
    return path

def wrap1(method):
    def fn(*args, **kwargs):
        path = stringtobytes(uncabspath(args[0]))
        return method(path, *args[1:], **kwargs)

    return fn

def wrap2(method):
    def fn(*args, **kwargs):
        src = stringtobytes(uncabspath(args[0]))
        dst = stringtobytes(uncabspath(args[1]))
        return method(src, dst, *args[2:], **kwargs)

    return fn

import ctypes, ctypes.wintypes
 
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_INVALID_HANDLE_VALUE = -1
_BAN = ('.', '..')

_ERROR_FILE_NOT_FOUND = 0x2
_ERROR_PATH_NOT_FOUND = 0x3
_ERROR_ALREADY_EXISTS = 0xB7
 
_errmap = {
        _ERROR_PATH_NOT_FOUND: errno.ENOENT,
        _ERROR_ALREADY_EXISTS: errno.EEXIST
}

_FindFirstFile = ctypes.windll.kernel32.FindFirstFileA
_FindNextFile  = ctypes.windll.kernel32.FindNextFileA
_FindClose     = ctypes.windll.kernel32.FindClose
_GetLastError  = ctypes.windll.kernel32.GetLastError
_CreateDirectory = ctypes.windll.kernel32.CreateDirectoryA



def lfnlistdir(path):
    '''Wrap os.listdir with a version that handles long UNC paths.
    The original version handles UNC format ok, but breaks if the path is
    longer than MAX_PATH.
    Contrary to the documentation available on the web, the use of long-UNC
    paths has been possible with both the FindFiles and FindFilesW families of
    functions since Windows XP, so we use the 1-byte wide functions to be
    consistant with the rest of Hg by not requiring unicode.
    This may cause Windows95/2000 to still throw FileNameTooLong exceptions.'''
    path = uncabspath(path)
    out  = ctypes.wintypes.WIN32_FIND_DATAA()
    fldr = _FindFirstFile(os.path.join(path, "*"), ctypes.byref(out))
 
    result = []
    if fldr == _INVALID_HANDLE_VALUE:
        error = _GetLastError()
        if error != _ERROR_PATH_NOT_FOUND and error != _ERROR_FILE_NOT_FOUND:
            raise ValueError("invalid handle (%s, %s)! " % (path, error))
    try:
        while True:
           if not out.cFileName == ".." and not out.cFileName == ".":
               result.append(out.cFileName)
           if not _FindNextFile(fldr, ctypes.byref(out)):
               return result
    finally:
        _FindClose(fldr)

def lfnmkdir(path, mode=None):
    '''Replace os.mkdir with a version that handles long UNC paths.
    The original version handles UNC format ok, but breaks if the path is
    longer than MAX_PATH.
    Contrary to the documentation available on the web, the use of long-UNC
    paths has been possible with both the CreateDirectory and CreateDirectoryW
    families of functions since Windows XP, so we use the 1-byte wide
    functions to be consistant with the rest of Hg by not requiring unicode.
    This may cause Windows95/2000 to still throw FileNameTooLong exceptions.'''
    path = uncabspath(path)
    # second parameter is a security descriptor, mapping it up to our
    # "mode" parameter is non-trivial and hopefully unnecessary
    error = _CreateDirectory(path, None)
    if error == 0:
        error = _GetLastError()
        pyerrno = _errmap[error]
        raise OSError(pyerrno, "Error")

def _addmissingbackslash(path):
    if path.endswith(":"):
        path += "\\"
    return path

def wrapsplit(split):
    '''Wrap os.path.split with a version that handles UNC paths.
    The OS's version mostly handles UNC format ok, but breaks at the root
    of a drive.
    In other words, with the OS's version:
>>> os.path.split('\\\\?\\C:\\')
('\\\\?\\C:', '')
    This is a problem, because it means join and split aren't inverses of each
    other for UNC paths and is different behaviour than os.path.split("C:\\").
    Fixing this also fixes dirname which has the same problem.'''

    def lfnsplit(path):
        result = split(path)
        if result[0].endswith(":"):
            result = (result[0]+"\\", result[1])
        return result

    return lfnsplit

def wrapchdir(ui, chdir):
    '''Wrap os.chdir with a version that handles long paths.
    The Windows API has no SetCurrentDirectory function that takes a long
    UNC path, so we emulate it internally. See:
http://social.msdn.microsoft.com/Forums/en/windowsgeneraldevelopmentissues/thread/7998d7ec-cf5a-4b5e-a554-13fa855e4a3d

    Where possible, we still call the OS's chdir function, but if we get a
    long path we emit a warning and then emulate the chdir.
    This is possible because all wrapped functions go through uncabspath()
    which converts the path to an absolute path.'''

    def lfnchdir(path):
        path = os.path.abspath(path)
        if len(path) >= _maxdirpath:
            ui.warn(_(
         "warning: chdir to a long directory path (see hg help win32lfn):\n%s"
                     ) % path)
        else:
            chdir(path)
        path = uncabspath(path)
        if os.path.exists(path):
            # I'd like to use an environment variable so subprocesses get the
            # correct cwd, but python environ can't store environment vars in
            # a different encoding from the "current". This is probably never
            # going to work correctly for subprocess invocations anyway.
            global _cwd
            _cwd = path
        else:
            raise OSError(errno.ENOENT, _("Directory doesn't exist: %s") % path)

    return lfnchdir

def wrapgetcwd(getcwd):
    '''Wrap os.getcwd() This is needed because we have to emulate os.chdir
    for long paths since Windows provides no API function to set the current
    directory to a long path.'''

    def lfngetcwd():
        if _cwd:
            result = _cwd
        else:
            result = getcwd()
            # Should I un-UNC long directories here?
        return result

    return lfngetcwd

def uisetup(ui):
    #os.listdir = lfnlistdir
    #os.mkdir = lfnmkdir                            # Tested with 3.9.13, pretty sure no longer needed (os.mkdir seems to work fine with long UNC paths)
    #os.path.abspath = wrapabspath(os.path.abspath)
    #os.path.split = wrapsplit(os.path.split)       # Tested with 3.9.13, pretty sure no longer needed (os.path.split seems to properly handle \\\\?\\C:\\ now)
    
    os.path.isdir = wrap1(os.path.isdir)
    
    # No wrapping needed for os.makedirs
    
    #os.chdir = wrapchdir(ui, os.chdir)
    #os.getcwd = wrapgetcwd(os.getcwd)
    
    os.stat = wrap1(os.stat)
    os.lstat = wrap1(os.lstat)
    os.open = wrap1(os.open)
    os.chmod = wrap1(os.chmod)
    os.remove = wrap1(os.remove)
    os.unlink = wrap1(os.unlink)
    os.rmdir = wrap1(os.rmdir)
    os.removedirs = wrap1(os.removedirs)
    os.rename = wrap2(os.rename)
    os.renames = wrap2(os.renames)
    
    #required for hg archive command
    os.utime = wrap1(os.utime)
    
    builtins.open = wrap1(builtins.open)
    
    util.posixfile = wrap1(util.posixfile)
    util.makedirs = wrap1(util.makedirs)
    util.rename = wrap2(util.rename)
    util.copyfile = wrap2(util.copyfile)
    util.copyfiles = wrap2(util.copyfiles)
    
    #required for hg add and status (commands which use dirstate.walk())
    util.listdir = wrap1(util.listdir)
    
    try:
        from mercurial import windows
    
        windows.listdir = wrap1(windows.listdir)
        windows.posixfile = wrap1(windows.posixfile)
    except:
        from mercurial import osutil
    
        osutil.listdir = wrap1(osutil.listdir)
        osutil.posixfile = wrap1(osutil.posixfile)
    
    if hasattr(util, "unlinkpath"):
        util.unlinkpath = wrap1(util.unlinkpath)
    if hasattr(util, "unlink"):
        util.unlink = wrap1(util.unlink)

def list(ui, repo):
    for root, dirs, files in os.walk(repo.root, topdown=False):
        for dir in dirs:
            d = os.path.join(root, dir)
            if len(d) > _maxpath:
                ui.write(d + "\n")
        for file in files:
            f = os.path.join(root, file)
            l = len(f)
            if l >= _maxpath:
                ui.write(f + "\n")

def cleanDir(ui, repo, force=False):
    for root, dirs, files in os.walk(repo.root, topdown=False):
        for dir in dirs:
            d = os.path.join(root, dir)
            if len(d) > _maxpath:
                if not force:
                    c = ui.promptchoice(_("Delete %s (yn)?") % f,
                                    (_("&No"), _("&Yes")), 0)
                if force or c:
                    os.rmdir(d)
        for file in files:
            f = os.path.join(root, file)
            if len(f) >= _maxpath:
                if not force:
                    c = ui.promptchoice(_("Delete %s (yn)?") % f,
                                    (_("&No"), _("&Yes")), 0)
                if force or c:
                    if hasattr(util, "unlink"):
                        util.unlink(f)
                    else:
                        util.unlinkpath(f)

cmdtable = {}
command = registrar.command(cmdtable)
@command(b'lfn',
         [(b'c', b'clean', None,
               _('Prompt to delete files longer than MAX_PATH.')),
              (b'f', b'force', False,
               _('Delete all files with long names when cleaning.'))],
             _('hg lfn [--clean] [--force]'))
def lfn(ui, repo, clean=None, force=False):
    '''Search for or delete files in the working copy that are longer than
    MAX_PATH (260) characters.

    This may make it easier to deal with such files, since many Windows
    programs are unable to.'''
    if clean:
        cleanDir(ui, repo, force)
    else:
        list(ui, repo)

def bytestostring(string):
    if isinstance(string, bytes):
        string = string.decode('utf-8')
    return string

def stringtobytes(string):
    if isinstance(string, str):
        string = str.encode(string)
    return string
