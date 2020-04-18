import platform
import os, sys
from pathlib import Path

def isWindows():
    plat = platform.system()
    return (plat == 'Windows')

def isMac():
    plat = platform.system()
    return (plat == 'Darwin')

# check if a binary is available in the PATH
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ['PATH'].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

def split_list(alist, wanted_parts=1):
    length = len(alist)
    return [ alist[i*length // wanted_parts: (i+1)*length // wanted_parts]
             for i in range(wanted_parts) ]

def prepareGrassEnv():
    # sys.path (to be able to import grass.script)
    # find grass depending on the system
    if isWindows():
        pass
    elif isMac():
        pass
    else:
        for grassVersion in ['74', '75', '76', '77', '78', '79']:
            findRes = list(Path('/usr/lib/grass%s' % grassVersion).rglob('*r.thin*'))
            if len(findRes) > 0:
                thinPath = str(findRes[0])
                grassBasePath = os.path.dirname(os.path.dirname(thinPath))
                grassPythonPath = os.path.join(grassBasePath, 'etc', 'python')
                if grassPythonPath not in sys.path:
                    sys.path.append(grassPythonPath)
                break
        os.environ['GISBASE'] = grassBasePath

        libPathToAdd = os.path.join(grassBasePath, 'lib')
        existingLdLibraryPath = ''
        if 'LD_LIBRARY_PATH' in os.environ:
            existingLdLibraryPath = os.environ['LD_LIBRARY_PATH']
        if libPathToAdd not in existingLdLibraryPath.split(':'):
            os.environ['LD_LIBRARY_PATH'] = '%s:%s' % (existingLdLibraryPath, libPathToAdd)

        pyPathToAdd = os.path.join(grassBasePath, 'etc', 'python')
        existingPYTHONPATH = ''
        if 'PYTHONPATH' in os.environ:
            existingPYTHONPATH = os.environ['PYTHONPATH']
        if pyPathToAdd not in existingPYTHONPATH.split(':'):
            os.environ['PYTHONPATH'] = '%s:%s' % (existingPYTHONPATH, pyPathToAdd)

        grassBinPath = os.path.join(grassBasePath, 'bin')
        grassScriptPath = os.path.join(grassBasePath, 'scripts')
        existingPath = ''
        if 'PATH' in os.environ:
            existingPath = os.environ['PATH']
        if grassBinPath not in existingPath.split(':'):
            os.environ['PATH'] = '%s:%s' % (existingPath, grassBinPath)
            existingPath = os.environ['PATH']
        if grassScriptPath not in existingPath.split(':'):
            os.environ['PATH'] = '%s:%s' % (existingPath, grassScriptPath)