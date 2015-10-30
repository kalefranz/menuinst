# Copyright (c) 2008-2011 by Enthought, Inc.
# Copyright (c) 2013 Continuum Analytics, Inc.
# All rights reserved.

from __future__ import absolute_import

from functools import partial
import os
from os.path import expanduser, isdir, join, exists
import sys

from .utils import rm_empty_dir, rm_rf
from .csidl import get_folder_path
from .winshortcut import create_shortcut

mode = ('user' if exists(join(sys.prefix, '.nonadmin')) else 'system')

quicklaunch_dir = join(get_folder_path('CSIDL_APPDATA'),
                       "Microsoft", "Internet Explorer", "Quick Launch")

if mode == 'system':
    desktop_dir = get_folder_path('CSIDL_COMMON_DESKTOPDIRECTORY')
    start_menu = get_folder_path('CSIDL_COMMON_PROGRAMS')
else:
    desktop_dir = get_folder_path('CSIDL_DESKTOPDIRECTORY')
    start_menu = get_folder_path('CSIDL_PROGRAMS')


def quoted(s):
    """
    quotes a string if necessary.
    """
    # strip any existing quotes
    s = s.strip(u'"')
    if u' ' in s or u'/' in s:
        return u'"%s"' % s
    else:
        return s


def substitute_env_variables(text, env_prefix=sys.prefix, env_name=None):
    # When conda is using Menuinst, only the root Conda installation ever calls menuinst.  Thus,
    #    these calls to sys refer to the root Conda installation, NOT the child environment
    py_major_ver = sys.version_info[0]
    py_bitness = 8 * tuple.__itemsize__

    for a, b in [
        ('${PREFIX}', env_prefix),
        ('${ROOT_PREFIX}', sys.prefix),
        ('${PYTHON_SCRIPTS}', os.path.normpath(join(env_prefix, 'Scripts')).replace("\\", "/")),
        ('${MENU_DIR}', join(env_prefix, 'Menu')),
        ('${PERSONALDIR}', get_folder_path('CSIDL_PERSONAL')),
        ('${USERPROFILE}', get_folder_path('CSIDL_PROFILE')),
        ('${ENV_NAME}', env_name if env_name else ""),
        ('${PY_VER}', str(py_major_ver)),
        ('${PLATFORM}', "(%s-bit)" % py_bitness),
        ]:
        text = text.replace(a, b)
    return text


class Menu(object):
    def __init__(self, name, prefix=sys.prefix):
        self.path = join(start_menu, substitute_env_variables(name))

    def create(self):
        if not isdir(self.path):
            os.mkdir(self.path)

    def remove(self):
        rm_empty_dir(self.path)


def get_python_args_for_subprocess(prefix, args, cmd):
    path_addon = os.path.pathsep.join([prefix,
                                       os.path.join(prefix, "Scripts"),
                                       os.path.join(prefix, "Library", "bin")])
    return ['-c', "import subprocess;import os;env=os.environ.copy();"
                  "env['PATH']=os.path.pathsep.join(['{path_addon}', env['PATH']]);"
                  "subprocess.call(['{cmd}', '{args}'], env=env)".format(path_addon=path_addon, cmd=cmd,
                                                                            args="', '".join(args)).replace("\\", "/")]

class ShortCut(object):
    def __init__(self, menu, shortcut, target_prefix, env_name, env_setup_cmd):
        """
        Prefix is the system prefix to be used -- this is needed since
        there is the possibility of a different Python's packages being managed.
        """
        self.menu = menu
        self.shortcut = shortcut
        self.prefix = target_prefix
        self.env_name = env_name
        self.env_setup_cmd = env_setup_cmd if env_setup_cmd else "activate %s" % self.prefix

    def remove(self):
        self.create(remove=True)

    def create(self, remove=False):
        args = []
        if "pywscript" in self.shortcut:
            cmd = join(self.prefix, "pythonw.exe").replace("\\", "/")
            args = self.shortcut["pywscript"].split()
            args = get_python_args_for_subprocess(self.prefix, args, cmd)
        elif "pyscript" in self.shortcut:
            cmd = join(self.prefix, "python.exe").replace("\\", "/")
            args = self.shortcut["pyscript"].split()
            args = get_python_args_for_subprocess(self.prefix, args, cmd)
        elif "webbrowser" in self.shortcut:
            cmd = join(sys.prefix, 'pythonw.exe')
            args = ['-m', 'webbrowser', '-t', self.shortcut['webbrowser']]
        elif "script" in self.shortcut:
            cmd = self.shortcut["script"].replace('/', '\\')
            args = self.shortcut["pyscript"].split()
            args = get_python_args_for_subprocess(self.prefix, args, cmd)
            cmd = join(sys.prefix, "pythonw.exe").replace("\\", "/")
        elif "system" in self.shortcut:
            cmd = substitute_env_variables(self.shortcut["system"],
                                             env_prefix=self.prefix,
                                             env_name=self.env_name).replace('/', '\\')
            args = self.shortcut['scriptargument']
        else:
            raise Exception("Nothing to do: %r" % self.shortcut)

        workdir = self.shortcut.get('workdir', '')
        icon = self.shortcut.get('icon', '')

        args = [substitute_env_variables(s, env_prefix=self.prefix, env_name=self.env_name) for s in args]
        workdir = substitute_env_variables(workdir, env_prefix=self.prefix, env_name=self.env_name)
        icon = substitute_env_variables(icon, env_prefix=self.prefix, env_name=self.env_name)

        # Fix up the '/' to '\'
        workdir = workdir.replace('/', '\\')
        icon = icon.replace('/', '\\')

        # Create the working directory if it doesn't exist
        if workdir:
            if not isdir(workdir):
                os.makedirs(workdir)
        else:
            workdir = expanduser('~')

        # Menu link
        dst_dirs = [self.menu.path]

        # Desktop link
        if self.shortcut.get('desktop'):
            dst_dirs.append(desktop_dir)

        # Quicklaunch link
        if self.shortcut.get('quicklaunch'):
            dst_dirs.append(quicklaunch_dir)

        name_suffix = " ({})".format(self.env_name) if self.env_name else ""
        for dst_dir in dst_dirs:
            dst = join(dst_dir, self.shortcut['name'] + name_suffix + '.lnk')
            if remove:
                rm_rf(dst)
            else:
                # The API for the call to 'create_shortcut' has 3
                # required arguments (path, description and filename)
                # and 4 optional ones (args, working_dir, icon_path and
                # icon_index).
                create_shortcut(
                    u'' + quoted(cmd),
                    u'' + self.shortcut['name'] + name_suffix,
                    u'' + dst,
                    u' '.join(quoted(arg) for arg in args),
                    u'' + workdir,
                    u'' + icon,
                )
