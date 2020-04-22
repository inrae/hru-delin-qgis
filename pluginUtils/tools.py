import platform
import os, sys
from pathlib import Path
import subprocess

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
    grassBasePath = None
    # sys.path (to be able to import grass.script)
    # find grass depending on the system
    if isWindows():
        for grassVersion in ['74', '75', '76', '77', '78', '79']:
            try:
                grassBasePath = subprocess.check_output(['grass%s.bat' % grassVersion, '--config', 'path'], shell=True).decode('utf-8').rstrip(os.linesep)
                break
            except Exception as e:
                pass
        print('found winwin %s !!!'%grassBasePath)

    elif isMac():
        pass
    else:
        grassBasePath = subprocess.check_output(['grass', '--config', 'path']).decode('utf-8').rstrip(os.linesep)
        print('found first %s !!!'%grassBasePath)
        if grassBasePath == None:
            for grassVersion in ['74', '75', '76', '77', '78', '79']:
                findRes = list(Path('/usr/lib/grass%s' % grassVersion).rglob('*r.thin*'))
                if len(findRes) > 0:
                    thinPath = str(findRes[0])
                    grassBasePath = os.path.dirname(os.path.dirname(thinPath))
                    break

    if grassBasePath == None:
        print('GRASS not found on your system')
        raise Exception('GRASS not found on your system')
        return

    grassPythonPath = os.path.join(grassBasePath, 'etc', 'python')
    if grassPythonPath not in sys.path:
        sys.path.append(grassPythonPath)
    os.environ['GISBASE'] = grassBasePath

    existingPYTHONPATH = ''
    if 'PYTHONPATH' in os.environ:
        existingPYTHONPATH = os.environ['PYTHONPATH']
    if grassPythonPath not in existingPYTHONPATH.split(os.pathsep):
        os.environ['PYTHONPATH'] = '%s%s%s' % (existingPYTHONPATH, os.pathsep, grassPythonPath)

    libPathToAdd = os.path.join(grassBasePath, 'lib')
    existingLdLibraryPath = ''
    if 'LD_LIBRARY_PATH' in os.environ:
        existingLdLibraryPath = os.environ['LD_LIBRARY_PATH']
    if libPathToAdd not in existingLdLibraryPath.split(os.pathsep):
        os.environ['LD_LIBRARY_PATH'] = '%s%s%s' % (existingLdLibraryPath, os.pathsep, libPathToAdd)

    grassBinPath = os.path.join(grassBasePath, 'bin')
    grassScriptPath = os.path.join(grassBasePath, 'scripts')
    existingPath = ''
    if 'PATH' in os.environ:
        existingPath = os.environ['PATH']
    if grassBinPath not in existingPath.split(os.pathsep):
        os.environ['PATH'] = '%s%s%s' % (existingPath, os.pathsep, grassBinPath)
        existingPath = os.environ['PATH']
    if grassScriptPath not in existingPath.split(os.pathsep):
        os.environ['PATH'] = '%s%s%s' % (existingPath, os.pathsep, grassScriptPath)