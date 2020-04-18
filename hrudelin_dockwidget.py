# -*- coding: utf-8 -*-
"""
/***************************************************************************
 HruDelinDockWidget
                                 A QGIS plugin
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os, shutil, sys, time
from pathlib import Path
import tempfile, configparser
from zipfile import ZipFile
from collections import defaultdict
from multiprocessing import cpu_count
import numpy as np
from osgeo import gdal, ogr, osr
from osgeo.gdalnumeric import *
from osgeo.gdalconst import *

# resolve path inside plugin directory (to get included data like map color legends for example)
def resolve(name, basepath=None):
    if not basepath:
        basepath = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(basepath, name)

from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QFileDialog, QApplication, QMessageBox, QStyle
from PyQt5.QtCore import pyqtSignal, QFileInfo, pyqtRemoveInputHook

from qgis.core import *
from qgis._gui import *
import processing

from hrudelin.pluginUtils import layerstools
from hrudelin.pluginUtils.tools import isWindows, isMac, which, prepareGrassEnv

prepareGrassEnv()
from hrudelin.hrudelinCore.modules.hrudelin_1_init import main as main1
from hrudelin.hrudelinCore.modules.hrudelin_2_basins import main as main2

# this exception is used by the QgisTasks
class CancelException(Exception):
    pass

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'hrudelin_dockwidget_base.ui'))

class HruDelinDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    # here we initialize everything
    def __init__(self, parent, iface):
        """Constructor."""
        super(HruDelinDockWidget, self).__init__(parent)
        # Qgis interface, used to get main window, manipulate messageBar etc...
        self.iface = iface
        # can be set within the interface
        self.DEBUG = False
        # define strings used for layout groups in the interface
        self.groupLabels = {
            'input': self.tr('[hru-delin] Input data'),
            'step1':   self.tr('[hru-delin] Step1'),
            'step2':   self.tr('[hru-delin] Step2'),
            'step3':   self.tr('[hru-delin] Step3'),
            'step4':   self.tr('[hru-delin] Step4'),
            'results': self.tr('[hru-delin] Results'),
        }

        self.setupUi(self)

        # GUI initialization:
        # * element visibility
        # * connect events with methods)
        # * set button styles
        # * set most english strings
        # * create temp directory
        self.groupBoxMnt.setVisible(True)
        self.resetButton.setVisible(False)
        self.exportFrame.setVisible(False)
        self.exportDataFrame.setVisible(False)
        self.exportDataResultsCheck.setVisible(False)

        self.projectPathTitleLabel.setVisible(True)
        self.projectPathLabel.setVisible(True)
        self.changeProjectPathButton.setVisible(True)
        self.changeProjectPathButton.pressed.connect(self.changeProjectPath)
        self.mQgsFileDEM.fileChanged.connect(self.checkDEM)
        self.mQgsFileStudyArea.fileChanged.connect(self.checkStudyArea)
        #self.mQgsFileSubcatchment.fileChanged.connect(self.checkUserSubcatchment)
        self.resetButton.clicked.connect(self.resetProject)
        self.loadButton.clicked.connect(self.loadProject)
        self.debugCheck.stateChanged.connect(self.debugChanged)
        self.exportButton.clicked.connect(self.exportProjectConfig)
        self.exportDataButton.clicked.connect(self.exportProjectData)
        # help buttons
        style = self.subcatchmentHelpButton.style()
        self.projectPathHelpButton.setIcon(style.standardIcon(QStyle.SP_MessageBoxQuestion))
        self.exportHelpButton.setIcon(style.standardIcon(QStyle.SP_MessageBoxQuestion))
        self.exportDataHelpButton.setIcon(style.standardIcon(QStyle.SP_MessageBoxQuestion))
        self.subcatchmentHelpButton.setIcon(style.standardIcon(QStyle.SP_MessageBoxQuestion))
        self.subcatchmentHelpButton.setToolTip(self.tr('Manually provide area where computations are done'))
        self.studyHelpButton.setIcon(style.standardIcon(QStyle.SP_MessageBoxQuestion))
        self.studyHelpButton.setToolTip(self.tr('Outlet area to determine subcatchment where computations are done'))
        self.subcatchmentHelpButton.clicked.connect(self.help)
        self.studyHelpButton.clicked.connect(self.help)
        self.exportHelpButton.clicked.connect(self.help)
        self.projectPathHelpButton.clicked.connect(self.help)
        self.exportDataHelpButton.clicked.connect(self.help)

        # style
        self.inputScrollArea.setBackgroundRole(QPalette.Light)
        self.mQgsFileDEM.setBackgroundRole(QPalette.Light)
        self.mQgsFileStudyArea.setBackgroundRole(QPalette.Light)

        # translations
        self.tabWidget.setTabText(0, self.tr('Input files'))
        self.tabWidget.setTabText(1, self.tr('Export'))
        self.projectPathTitleLabel.setText(self.tr('Output directories location'))
        self.projectBox.setTitle(self.tr('Project'))
        self.groupBoxMnt.setTitle(self.tr('Digital elevation model'))
        self.demFileLabel.setText(self.tr('DEM'))
        self.studyAreaLabel.setText(self.tr('Study area'))
        self.subcatchmentLabel.setText(self.tr('Subcatchment'))
        self.changeProjectPathButton.setText(self.tr('Change'))
        self.resetButton.setText(self.tr('Reset project'))
        self.loadButton.setText(self.tr('Load Irip config file (.cfg)'))
        self.debugCheck.setText(self.tr('See all intermediate files\n(debug mode)'))
        self.exportDataResultsCheck.setText('Include results in exported archive')
        self.exportButton.setText('Export cfg file')
        self.exportDataButton.setText('Export portable config with input data')

        # just to make those strings appear in translation files
        vvw = self.tr('None')
        vw = self.tr('Very weak')
        w = self.tr('Weak')
        a = self.tr('Average')
        s = self.tr('Strong')
        vs = self.tr('Very strong')

        self.layers = defaultdict(list)

        self.tempDir = tempfile.TemporaryDirectory()
        # set new default temp dir
        self.projectPath = os.path.join(self.tempDir.name, self.tr('temporary'))
        self.projectPathLabel.setText(self.projectPath.replace('\\', '/'))

    # called when closing the dock widget
    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()
        self.resetProject()

    # called when clicking on help buttons
    # just display an alert message box with help
    def help(self):
        oName = self.sender().objectName()
        title = self.tr('Help')
        message = self.tr('No help found')
        if oName == 'subcatchmentHelpButton':
            title = self.tr('Help for subcatchment area')
            message = self.tr('Set this if you already know the area where you want to make the computations.\n\nIf you provide a value here, study area field will be ignored.')
        elif oName == 'studyHelpButton':
            title = self.tr('Help for study area')
            message = self.tr('If you set this, IRIP will compute the related subcatchment area which is the area flowing to the study area.\n\nIf you provide a value here, subcatchment field will be ignored.')
        elif oName == 'exportHelpButton':
            title = self.tr('Help for export')
            message = self.tr('You can export project configuration (file paths) to a config (.cfg) file. You can then load this file to run Irip again with this configuration.\n\nThis is usefull to perform the same analysis multiple times or to change just one input file and re-run an analysis.')
        elif oName == 'exportDataHelpButton':
            title = self.tr('Help for export data')
            message = self.tr('This button allows you to export an archive containing all input data files and a config (.cfg) file.\n\nYou can then send this archive to someone who will directly be able to run the analysis with Irip plugin.')
        if oName == 'projectPathHelpButton':
            title = self.tr('Help for project path')
            message = self.tr('This is the path where result directories will be created (results, indicators, tmp and work)')
        if oName == 'areaThrsHelpButton':
            title = self.tr('Help for area threshold')
            message = self.tr('Minimum drained area size considered to produce transfer and accumulation indicators')
        if oName == 'nullCurveHelpButton':
            title = self.tr('Help for ')
            message = self.tr('Until which value a curve is considered as plane?')

        QMessageBox.question(
            self.iface.mainWindow(),
            title,
            message,
            QMessageBox.Ok
        )

    def debugChanged(self):
        self.DEBUG = self.debugCheck.isChecked()

    ########## manage layers ###########

    def createGroup(self, gid, project):
        root = project.layerTreeRoot()
        label = self.groupLabels[gid]
        groupNode = root.findGroup(label)
        # create if it does not exist
        if groupNode is None:
            groupNode = root.insertGroup(0, self.groupLabels[gid])
            #groupNode.setExpanded(False)

    def deleteGroup(self, gid):
        root = QgsProject.instance().layerTreeRoot()
        label = self.groupLabels[gid]
        groupNode = root.findGroup(label)
        if groupNode is not None:
            root.removeChildNode(groupNode)

    def addToGroup(self, layer, project, gid, expanded=True):
        root = project.layerTreeRoot()

        # add but not to the legend
        project.addMapLayer(layer, False)

        label = self.groupLabels[gid]
        groupNode = root.findGroup(label)
        if groupNode is None:
            self.createGroup(gid, project)
        groupNode = root.findGroup(label)

        layerNode = groupNode.insertLayer(0, layer)
        if not expanded:
            layerNode.setExpanded(False)

    def removeFromGroup(self, layer, gid):
        root = QgsProject.instance().layerTreeRoot()
        label = self.groupLabels[gid]
        groupNode = root.findGroup(label)
        if groupNode is not None:
            groupNode.removeLayer(layer)
        if isWindows() or isMac():
            # thanks to windows file locks, we need to do that to make sure we free the lock
            # and shp* files can be deleted by Python
            QgsProject.instance().addMapLayer(layer)
        # anyway try to remove it the usual way
        QgsProject.instance().removeMapLayer(layer)

    def removeLayersByTag(self, tag):
        #if tag in ['dem', 'study', 'subcatchment']:
        #    gid = 'general'
        #elif tag in ['landuse']:
        #    gid = 'landuse'
        #elif tag in ['soil']:
        #    gid = 'soil'
        #elif tag in ['linear']:
        #    gid = 'linear'
        #elif tag in ['indicator']:
        #    gid = 'indicator'

        gid = tag

        for layer in self.layers[tag]:
            # just in case layer has already been manually removed
            # underlying c++ object does not exist anymore and we get a runtime exception
            try:
                self.removeFromGroup(layer, gid)
                del layer
            except Exception as e:
                print('Exception when removing layer')
                print('%s'%e)
        self.layers[tag] = []

    def displayLayer(self, params, targetProject=None):
        if targetProject is None:
            project = QgsProject.instance()
        else:
            project = targetProject

        layerType = params['type']
        layerPath = params['path']
        layerName = params['name']
        expanded = params['expanded'] if 'expanded' in params else False
        # default tag is 'various'
        tag = params['tag'] if 'tag' in params else 'various'
        # if checked not specified : True
        layerChecked = params['checked'] if 'checked' in params else True

        if layerType == 'vector':
            self.iface.mainWindow().blockSignals(True)
            layer = QgsVectorLayer(layerPath, layerName)
            self.iface.mainWindow().blockSignals(False)
            layer.setCrs(self.projObj)
            if 'style' in params:
                layer.loadNamedStyle(params['style'])
        else:
            # let's temporarily shut down the warnings when loading a raster
            # because we set a projection anyway
            self.iface.mainWindow().blockSignals(True)
            layer = QgsRasterLayer(layerPath, layerName)
            self.iface.mainWindow().blockSignals(False)

            if 'palette' in params:
                classes = QgsPalettedRasterRenderer.classDataFromFile(params['palette'])
                for c in classes:
                    c.label = self.tr(c.label)
                renderer = QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes)
                layer.setRenderer(renderer)

            layer.setCrs(self.projObj)

        # put it in the related group
        self.addToGroup(layer, project, tag, expanded)

        if not layerChecked:
            item = project.layerTreeRoot().findLayer(layer.id())
            if item:
                item.setItemVisibilityChecked(False)
            else:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    self.tr('item not found'),
                    self.tr('item %s not found'%layerName)
                )

        if targetProject is not None:
            # we store the layers by tag to be able to remove them later
            self.layers[tag].append(layer)

        return layer

    # save main QGIS project or a custom one
    def saveProject(self, layerDictList, savePath):
        # if no layers provided, just save current main QGIS project
        if layerDictList is None:
            project = QgsProject.instance()
        # if some layers provided, save a project displaying them
        else:
            project = QgsProject()
            for lp in layerDictList:
                self.displayLayer(lp, project)

        project.write(savePath)

    ############## END manage layers #############

    # load a config file and launch a full run
    def loadProject(self):
        self.resetProject()

        projectFilePath, filter = QFileDialog.getOpenFileName(self, self.tr('Project config file'), None, 'Config files (*.cfg)')
        if projectFilePath == '':
            return
        self.loadProjectStartTime = time.time()

        projectFileDir = os.path.dirname(projectFilePath)
        self.projectFileDir = projectFileDir
        config = configparser.ConfigParser()
        config.read(projectFilePath)
        self.projectFilePath = projectFilePath

        # dir_in is absolute or relative to config file parent directory
        dir = config['dir_in']['dir']
        if not os.path.isabs(dir):
            dir = os.path.join(projectFileDir, dir)
        cfgDemPath = os.path.join(dir, config['files_in']['dem'])

        ## studyarea is absolute or relative to dir_in
        #cfgStudyareaPath = config['files_in']['studyarea'] if ('studyarea' in config['files_in']) else None
        #if cfgStudyareaPath != None and not os.path.isabs(cfgStudyareaPath):
        #    cfgStudyareaPath = os.path.join(dir, cfgStudyareaPath)
        #cfgStudyareaField = config['studyarea_parms']['studyarea_id'] if ('studyarea_parms' in config and 'studyarea_id' in config['studyarea_parms']) else None

        self.cfgFilesOutPath = config['dir_out']['files']
        if not os.path.isabs(self.cfgFilesOutPath):
            self.cfgFilesOutPath = os.path.join(projectFileDir, self.cfgFilesOutPath)

        self.cfgResultsOutPath = config['dir_out']['results']
        if not os.path.isabs(self.cfgResultsOutPath):
            self.cfgResultsOutPath = os.path.join(projectFileDir, self.cfgResultsOutPath)

        self.projectPath = os.path.dirname(self.cfgResultsOutPath)
        self.projectPathLabel.setText(self.projectPath.replace('\\', '/'))

        # now get the job done
        self.mQgsFileDEM.setFilePath(cfgDemPath)

        self.doStep1(True, self.step1FinishedAuto)

    # export a config file from current form state
    def exportProjectConfig(self):
        exportPath, filter = QFileDialog.getSaveFileName(self, self.tr('Export project config file'), None, '.cfg config files (*.cfg)')
        if not exportPath.endswith('.cfg'):
            exportPath = '%s.cfg'%exportPath

        exportDir = os.path.dirname(exportPath)
        if not os.access(exportDir, os.W_OK):
            QMessageBox.critical(
                self.iface.mainWindow(),
                self.tr('Export failed'),
                self.tr('Can''t write to directory %s'%exportDir)
            )
            return

        outDir = self.projectPath
        demPath = self.mQgsFileDEM.filePath()

        # export absolute path only
        config = configparser.ConfigParser()
        config['dir_in'] = {'dir': '/not.used.because.every.path.is.absolute'}
        config['dir_out'] = {'results': os.path.abspath(outDir)}
        config['files_in'] = {'dem': os.path.abspath(demPath)}

        with open(exportPath, 'w') as exportFile:
            config.write(exportFile)
        self.iface.messageBar().pushSuccess('HRU delin', self.tr('Config file successfully exported to %s' % exportPath))

    # save an archive with config file and input data
    # optionnally include result data
    def exportProjectData(self):
        exportArchivePath, filter = QFileDialog.getSaveFileName(self, self.tr('Export project data+config archive'), None, 'ZIP archives (*.zip)')
        if not exportArchivePath.endswith('.zip'):
            exportArchivePath = '%s.zip'%exportArchivePath

        exportDir = os.path.dirname(exportArchivePath)
        if not os.access(exportDir, os.W_OK):
            QMessageBox.critical(
                self.iface.mainWindow(),
                self.tr('Export failed'),
                self.tr('Can''t write to directory %s'%exportDir)
            )
            return

        outDir = self.projectPath
        demPath = self.mQgsFileDEM.filePath()

        # export relative path only
        config = configparser.ConfigParser()
        input_dir = 'input_data'
        output_dir = 'results_irip_plugin'

        config['dir_in'] = {'dir': input_dir}
        config['dir_out'] = {'results': output_dir}
        config['files_in'] = {'dem': os.path.basename(demPath)}

        tmpConfigPath = os.path.join(exportDir, 'tmpconfig.cfg')
        with open(tmpConfigPath, 'w') as tmpConfigFile:
            config.write(tmpConfigFile)

        # now produce the zip archive
        exportName = os.path.basename(exportArchivePath)
        inside_dir = '.'.join(exportName.split('.')[:-1])
        with ZipFile(exportArchivePath, 'w') as zipObj:
            zipObj.write(tmpConfigPath, os.path.join(inside_dir, 'hrudelin_config.cfg'))
            zipObj.write(demPath, os.path.join(inside_dir, input_dir, os.path.basename(demPath)))

            #if studyPath:
            #    zipObj.write(studyPath, os.path.join(inside_dir, input_dir, os.path.basename(studyPath)))
            #    if studyPath.split('.')[-1] == 'shp':
            #        studyPathNoExt = '.'.join(studyPath.split('.')[:-1])
            #        for ext in ['dbf', 'prj', 'shx', 'qpj']:
            #            shapeBonusPath = studyPathNoExt+'.'+ext
            #            if os.path.exists(shapeBonusPath):
            #                zipObj.write(shapeBonusPath, os.path.join(inside_dir, input_dir, os.path.basename(shapeBonusPath)))
            #else:
            #    zipObj.write(subcatchmentPath, os.path.join(inside_dir, input_dir, os.path.basename(subcatchmentPath)))
            #    if subcatchmentPath.split('.')[-1] == 'shp':
            #        subcatchmentPathNoExt = '.'.join(subcatchmentPath.split('.')[:-1])
            #        for ext in ['dbf', 'prj', 'shx', 'qpj']:
            #            shapeBonusPath = subcatchmentPathNoExt+'.'+ext
            #            if os.path.exists(shapeBonusPath):
            #                zipObj.write(shapeBonusPath, os.path.join(inside_dir, input_dir, os.path.basename(shapeBonusPath)))

            # here we also put the results directory in the archive
            # TODO adjust that
            if self.exportDataResultsCheck.isChecked():
                result_dir = self.tr('plugin_results')
                flist = [os.path.join(outDir, f) for f in os.listdir(outDir) if os.path.isfile(os.path.join(outDir, f))]
                for fPath in flist:
                    zipObj.write(fPath, os.path.join(inside_dir, result_dir, os.path.basename(fPath)))
                for dirName in ['tmp', 'indicators', 'results', 'work']:
                    flist = [os.path.join(outDir, dirName, f) for f in os.listdir(os.path.join(outDir, dirName)) if os.path.isfile(os.path.join(outDir, dirName, f))]
                    for fPath in flist:
                        zipObj.write(fPath, os.path.join(inside_dir, result_dir, dirName, os.path.basename(fPath)))
        # delete temporary config file
        os.remove(tmpConfigPath)

        self.iface.messageBar().pushSuccess('HRU delin', self.tr('Data+config archive successfully exported to %s'%exportArchivePath))

    # called when step1 process ended during a full run
    # the goal is to chain with the rest of the run
    def step1FinishedAuto(self):
        self.step1Finished()

        self.doStep2(True, self.step2FinishedAuto)

    # called when step2 ended during a full run
    # it will chain with the rest of the run
    def step2FinishedAuto(self):
        self.step2Finished()
        # launch all maps generation
        self.doStep3(False, self.step3FinishedAuto)

    def step3FinishedAuto(self):
        self.step3Finished()
        self.doStep4(False, self.step4FinishedAuto)

    def step4FinishedAuto(self):
        self.step4Finished()
        wholeProcessEndTime = time.time()
        print()
        print('[FULL PROCESS] %.2f'%(wholeProcessEndTime - self.loadProjectStartTime))

    # reset all layers and data related to the plugin
    def resetProject(self):
        self.exportFrame.setVisible(False)
        self.exportDataFrame.setVisible(False)
        self.exportDataResultsCheck.setVisible(False)
        # project
        self.changeProjectPathButton.setVisible(True)
        self.projectPathLabel.setText('')
        self.resetButton.setVisible(False)

        # mnt
        self.mQgsFileDEM.blockSignals(True)
        self.mQgsFileDEM.setFilePath('')
        self.mQgsFileDEM.blockSignals(False)

        # sub reset parts
        #self.resetMapButtons()

        self.tempDir = tempfile.TemporaryDirectory()

        # remove all layers?
        if len(QgsProject.instance().layerTreeRoot().layerOrder()) > 0:
            reply = QMessageBox.question(self.iface.mainWindow(), self.tr('Reset QGIS project'),
                self.tr('Do you want to reset the current QGIS project (remove all loaded layers)'),
                QMessageBox.Yes, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                QgsProject.instance().clear()

        # set new default dir
        self.projectPath = os.path.join(self.tempDir.name, self.tr('temporary'))
        self.projectPathLabel.setText(self.projectPath.replace('\\', '/'))

    # when click on "change"
    # allow user to choose where to write output files
    def changeProjectPath(self):
        hostDir = QFileDialog.getExistingDirectory(
            self,
            self.tr('Select where to write the result files')
        )
        if hostDir:
            self.projectPath = hostDir
            self.projectPathLabel.setText(self.projectPath.replace('\\', '/'))

    # create all needed directories in output directory
    # and create saga CMD output files
    def buildProjectEnvironment(self):
        self.resetButton.setVisible(True)
        #self.projectPath = QFileDialog.getExistingDirectory(self, self.tr('Select a folder')) + '/' + self.lineEditProjectName.text()
        # remove result directories if present
        if not os.path.exists(self.projectPath):
            os.mkdir(self.projectPath)

        self.intermDir = os.path.join(self.projectPath, 'hrudelin_intermediate')
        if os.path.exists(self.intermDir):
            shutil.rmtree(self.intermDir)
        os.mkdir(self.intermDir)

        self.finalDir = os.path.join(self.projectPath, 'hrudelin_final')
        if os.path.exists(self.finalDir):
            shutil.rmtree(self.finalDir)
        os.mkdir(self.finalDir)

    # called after having changed the DEM
    # reset all further Irip "chapters"
    # get project projection from the DEM file
    def checkDEM(self):
        self.changeProjectPathButton.setVisible(False)

        # reset study and subcatchment
        # TODO hide doStep* buttons
        #self.doStep1Btn.setVisible(False)
        self.mQgsFileStudyArea.blockSignals(True)
        self.mQgsFileSubcatchment.blockSignals(True)
        self.mQgsFileStudyArea.setFilePath('')
        self.mQgsFileSubcatchment.setFilePath('')
        self.mQgsFileStudyArea.blockSignals(False)
        self.mQgsFileSubcatchment.blockSignals(False)

        for tag in ['step1', 'step2', 'step3', 'step4', 'results']:
            self.removeLayersByTag(tag)
            self.deleteGroup(tag)

        # sub resets
        #self.resetLanduse()

        self.buildProjectEnvironment()

        self.demPath = self.mQgsFileDEM.filePath()
        self.demName = os.path.basename(self.demPath)
        if os.path.exists(self.demPath):
            # we just get the projection
            fd = gdal.Open(self.demPath)
            osrProj = osr.SpatialReference(wkt=fd.GetProjection())
            self.projNum = int(osrProj.GetAttrValue('AUTHORITY', 1))
            self.proj = 'EPSG:%s' % self.projNum

            self.projObj = QgsCoordinateReferenceSystem(self.projNum, QgsCoordinateReferenceSystem.EpsgCrsId)
            self.demLayer = self.displayLayer({
                'type': 'raster',
                'path': self.demPath,
                'name': self.demName,
                'tag': 'input',
                'checked': True
            })

            ## new way to read projection
            #dem_rs   = gdal.Open(self.demPath)
            #self.gdalProj = dem_rs.GetProjection()

            #print("proj " + str(self.proj))
            #print("projNum " + str(self.projNum))

    # when changing study area, potentially convert it
    def checkStudyArea(self):
        self.removeLayersByTag('study')
        self.removeLayersByTag('subcatchment')
        self.resetLanduse()
        self.resetSoil()
        self.resetLinears()
        self.resetMapButtons()

        self.studyAreaPath = self.mQgsFileStudyArea.filePath()
        self.studyAreaName = os.path.basename(self.studyAreaPath)
        ## TODO adjust all that...
        #if not os.path.exists(self.studyAreaPath):
        #    self.generateCatchmentBtn.setVisible(False)
        #else:
        #    # in any case, we get rid of SUBCATCHMENT if study area is set
        #    self.mQgsFileSubcatchment.setFilePath('')

        #    if self.studyAreaName.split('.')[-1] in ['shp', 'gpkg']:
        #        self.studyAreaLayer = self.displayLayer({
        #            'type': 'vector',
        #            'path': self.studyAreaPath,
        #            'name': self.studyAreaName,
        #            'tag': 'study',
        #            'checked': True
        #        })
        #        self.generateCatchmentBtn.setVisible(True)
        #    elif self.studyAreaName.split('.')[-1] in ['tif', 'map']:
        #        self.studyAreaLayer = self.displayLayer({
        #            'type': 'raster',
        #            'path': self.studyAreaPath,
        #            'name': self.studyAreaName,
        #            'tag': 'study',
        #            'checked': True
        #        })
        #        self.generateCatchmentBtn.setVisible(True)
        #    else:
        #        self.generateCatchmentBtn.setVisible(False)

    # create the QgsTask and launch it
    # successMethod will be called after the QgsTask has successfully finished
    def launchTask(self, taskName, processMethodList, successMethod=None, errorMethod=None):
        task = HruDelinTask(taskName, self, processMethodList)
        self.task = task

        # configure the QgsMessageBar
        messageBar = self.iface.messageBar().createMessage(self.tr('Running %s...' % taskName), )
        progressBar = QtWidgets.QProgressBar()
        progressBar.setAlignment(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
        cancelButton = QtWidgets.QPushButton()
        cancelButton.setText(self.tr('Cancel'))
        cancelButton.clicked.connect(task.cancel)
        messageBar.layout().addWidget(progressBar)
        messageBar.layout().addWidget(cancelButton)
        self.iface.messageBar().pushWidget(messageBar, Qgis.Info)
        self.messageBar = messageBar

        # start the worker in a new thread
        if successMethod != None:
            task.taskCompleted.connect(successMethod)
        if errorMethod != None:
            task.taskTerminated.connect(errorMethod)
        task.progressChanged.connect(progressBar.setValue)
        task.displayLayer.connect(self.displayLayer)

        QgsApplication.taskManager().addTask(task)
        # WOW this "was" necessary to avoid a crash
        #print('task ADDED')

    # receive on click event OR is called by load process
    def doStep1(self, uselessBool, successMethod=None):
        #self.generateCatchmentBtn.setVisible(False)
        #self.resetLanduse()
        #self.resetLinears()
        #self.resetSoil()
        self.removeLayersByTag('step1')

        if successMethod == None:
            taskSuccessMethod = self.step1Finished
        else:
            taskSuccessMethod = successMethod
        self.launchTask('Step 1', [self.processStep1], taskSuccessMethod, self.step1Error)

    # called when the task has finished with success in a manual run
    def step1Finished(self):
        self.iface.messageBar().popWidget(self.messageBar)
        self.iface.messageBar().pushSuccess('HRU delin', self.tr('Step 1 success'))

        ## show next GUI elements
        #self.groupBoxLanduse.setVisible(True)
        #self.groupBoxIripPlus.setVisible(True)
        #self.landuseLegend1Frame.setVisible(False)
        #self.landuseLegend2Frame.setVisible(False)

    # called when the task returns False
    # determine if the task was canceled or if it crashed
    def step1Error(self):
        self.iface.messageBar().popWidget(self.messageBar)
        QgsMessageLog.logMessage('Exception: {}'.format(self.task.exception),
                                 'HRU delin', Qgis.Critical)
        try:
            raise self.task.exception
        except CancelException as e:
            self.iface.messageBar().pushMessage(self.tr('Step 1 task TERMINATED because it was canceled'))
        except Exception as e:
            self.iface.messageBar().pushCritical('HRU delin', self.tr('Step 1 task problem. See StackTrace for more details'))
            raise e

    def doStep2(self, uselessBool, successMethod=None):
        self.removeLayersByTag('step2')

        if successMethod == None:
            taskSuccessMethod = self.step2Finished
        else:
            taskSuccessMethod = successMethod
        self.launchTask('Step 2', [self.processStep2], taskSuccessMethod, self.step2Error)

    # called when the task has finished with success in a manual run
    def step2Finished(self):
        self.iface.messageBar().popWidget(self.messageBar)
        self.iface.messageBar().pushSuccess('HRU delin', self.tr('Step 2 success'))

        # TODO we could add layers here...

        ## show next GUI elements
        #self.groupBoxLanduse.setVisible(True)
        #self.groupBoxIripPlus.setVisible(True)
        #self.landuseLegend1Frame.setVisible(False)
        #self.landuseLegend2Frame.setVisible(False)

    # called when the task returns False
    # determine if the task was canceled or if it crashed
    def step2Error(self):
        self.iface.messageBar().popWidget(self.messageBar)
        QgsMessageLog.logMessage('Exception: {}'.format(self.task.exception),
                                 'HRU delin', Qgis.Critical)
        try:
            raise self.task.exception
        except CancelException as e:
            self.iface.messageBar().pushMessage(self.tr('Step 2 task TERMINATED because it was canceled'))
        except Exception as e:
            self.iface.messageBar().pushCritical('HRU delin', self.tr('Step 2 task problem. See StackTrace for more details'))
            raise e

    def doStep3(self, uselessBool, successMethod=None):
        #self.generateCatchmentBtn.setVisible(False)
        #self.resetLanduse()
        #self.resetLinears()
        #self.resetSoil()
        self.removeLayersByTag('step3')

        if successMethod == None:
            taskSuccessMethod = self.step3Finished
        else:
            taskSuccessMethod = successMethod
        self.launchTask('Step 3', [self.processStep3], taskSuccessMethod, self.step3Error)

    # called when the task has finished with success in a manual run
    def step3Finished(self):
        self.iface.messageBar().popWidget(self.messageBar)
        self.iface.messageBar().pushSuccess('HRU delin', self.tr('Step 3 success'))

        # TODO we could add layers here...

        ## show next GUI elements
        #self.groupBoxLanduse.setVisible(True)
        #self.groupBoxIripPlus.setVisible(True)
        #self.landuseLegend1Frame.setVisible(False)
        #self.landuseLegend2Frame.setVisible(False)

    # called when the task returns False
    # determine if the task was canceled or if it crashed
    def step3Error(self):
        self.iface.messageBar().popWidget(self.messageBar)
        QgsMessageLog.logMessage('Exception: {}'.format(self.task.exception),
                                 'HRU delin', Qgis.Critical)
        try:
            raise self.task.exception
        except CancelException as e:
            self.iface.messageBar().pushMessage(self.tr('Step 3 task TERMINATED because it was canceled'))
        except Exception as e:
            self.iface.messageBar().pushCritical('HRU delin', self.tr('Step 3 task problem. See StackTrace for more details'))
            raise e

    def doStep4(self, uselessBool, successMethod=None):
        #self.generateCatchmentBtn.setVisible(False)
        #self.resetLanduse()
        #self.resetLinears()
        #self.resetSoil()
        self.removeLayersByTag('step4')

        if successMethod == None:
            taskSuccessMethod = self.step4Finished
        else:
            taskSuccessMethod = successMethod
        self.launchTask('Step 4', [self.processStep4], taskSuccessMethod, self.step4Error)

    def step4Finished(self):
        self.exportDataResultsCheck.setVisible(True)
        self.iface.messageBar().popWidget(self.messageBar)
        self.iface.messageBar().pushSuccess('HRU delin', self.tr('Step 4 success'))

        # add result layers here

        # TODO adjust QGIS project saving
        ## save a small QGIS project with result maps only
        #resultsParamList = [
        #    {
        #        'type': 'vector',
        #        'path': self.resultHruPath,
        #        'name': self.tr('HRUs'),
        #        'tag': 'results',
        #        'expanded': False,
        #    },
        #    {
        #        'type': 'vector',
        #        'path': self.resultReachPath,
        #        'name': self.tr('Reachs'),
        #        'tag': 'results',
        #        'expanded': False,
        #    },
        #]
        #self.saveProject(resultsParamList, os.path.join(self.resultsDir, 'hru-delin_final.qgz'))

        ## save a big QGIS project file in results dir (to keep palettes)
        #paramList = []
        #paramList.append({
        #    'type': 'vector',
        #    'path': self.catchmentVectorPath,
        #    'name': self.tr('catchment vector'),
        #    'tag': 'subcatchment'
        #})

        #paramList.extend(resultsParamList)
        #self.saveProject(paramList, os.path.join(self.projectPath, 'hru-delin_all_results.qgz'))

    def step4Error(self):
        self.iface.messageBar().popWidget(self.messageBar)
        QgsMessageLog.logMessage('Exception: {}'.format(self.task.exception),
                                 'HRU delin', Qgis.Critical)
        try:
            raise self.task.exception
        except CancelException as e:
            self.iface.messageBar().pushMessage(self.tr('Step 4 task TERMINATED because it was canceled'))
        except Exception as e:
            self.iface.messageBar().pushCritical('HRU delin', self.tr('Step 4 task problem. See StackTrace for more details'))
            raise e

    # here we get serious
    def processStep1(self, task):
        task.setProgress(0)

        # do the same job as hrudelin bash script which launch python modules
        if os.path.exists(self.cfgFilesOutPath):
            shutil.rmtree(self.cfgFilesOutPath)
        os.mkdir(self.cfgFilesOutPath)

        if os.path.exists(self.cfgResultsOutPath):
            shutil.rmtree(self.cfgResultsOutPath)
        os.mkdir(self.cfgResultsOutPath)

        tmpPath = os.path.join(self.projectFileDir, 'tmp')
        if os.path.exists(tmpPath):
            shutil.rmtree(tmpPath)
        os.mkdir(tmpPath)

        # run the mzfc
        main1(self.projectFilePath)

        # display layers
        for fPath in Path(self.cfgFilesOutPath).rglob('*step1*.tif'):
            strPath = str(fPath)
            task.displayLayer.emit({
                'type': 'raster',
                'path': strPath,
                'name': os.path.basename(strPath),
                'tag': 'step1'
            })
        for fPath in Path(self.cfgFilesOutPath).rglob('*step1*.shp'):
            strPath = str(fPath)
            task.displayLayer.emit({
                'type': 'vector',
                'path': strPath,
                'name': os.path.basename(strPath),
                'tag': 'step1'
            })

        return True

    def processStep2(self, task):
        task.setProgress(0)

        for fPath in Path(self.cfgFilesOutPath).rglob('step2*.tif'):
            os.remove(str(fPath))
        for fPath in Path(self.cfgFilesOutPath).rglob('step3*.tif'):
            os.remove(str(fPath))

        if os.path.exists(self.cfgResultsOutPath):
            shutil.rmtree(self.cfgResultsOutPath)
        os.mkdir(self.cfgResultsOutPath)

        # run the mzfc
        for progress in main2(self.projectFilePath, cpu_count(), True):
            task.setProgress(progress)

        # display layers
        for fPath in Path(self.cfgFilesOutPath).rglob('*step2*.tif'):
            strPath = str(fPath)
            task.displayLayer.emit({
                'type': 'raster',
                'path': strPath,
                'name': os.path.basename(strPath),
                'tag': 'step2'
            })
        for fPath in Path(self.cfgFilesOutPath).rglob('*step2*.shp'):
            strPath = str(fPath)
            task.displayLayer.emit({
                'type': 'vector',
                'path': strPath,
                'name': os.path.basename(strPath),
                'tag': 'step2'
            })

        return True

    def processStep3(self, task):
        task.setProgress(0)

        #HruDelinCore.step1(self.configFilePath)
        print('inside STEP 3 task')

        return True

    def processStep4(self, task):
        task.setProgress(0)

        #HruDelinCore.step1(self.configFilePath)
        print('inside STEP 4 task')

        return True


class HruDelinTask(QgsTask):
    displayLayer = QtCore.pyqtSignal(object)
    def __init__(self, desc, dockwidget, methodsToCall):
        QgsTask.__init__(self, desc, QgsTask.CanCancel)
        self.dockwidget = dockwidget
        self.methodsToCall = methodsToCall
        self.exception = None
        self.desc = desc

    def run(self):
        #print('task starting')
        ret = True
        try:
            self.setProgress(2)
            for method in self.methodsToCall:
                ret = method(self)
        except Exception as e:
            self.exception = e
            return False
        #print('task finishing')
        return ret

    # this method is not always called, we catch the signals anyway
    def finished(self, result):
        #print('task finished method, result: %s'%result)
        pass

    def cancel(self):
        self.dockwidget.iface.messageBar().pushMessage(
            self.desc + ': ' + self.dockwidget.tr('Task canceled, killing it might take some time. Close QGIS to kill it.')
        )
        super().cancel()
