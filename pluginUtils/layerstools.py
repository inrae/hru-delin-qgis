import sys, os
import processing
from osgeo import ogr, osr, gdal, gdalconst
from osgeo.gdalnumeric import *
from osgeo.gdalconst import *
import numpy as np
#import gdal

def rasterize(model, vector, field, rasterOut, proj, dataTypeNumber=3, burnValue=None):
    extent = model.extent()
    xmin = extent.xMinimum()
    xmax = extent.xMaximum()
    ymin = extent.yMinimum()
    ymax = extent.yMaximum()

    pixelXsize = model.rasterUnitsPerPixelX()
    pixelYsize = model.rasterUnitsPerPixelY()

    params = {
        'INPUT': vector,
        'FIELD': field,
        'UNITS': 1,
        'WIDTH': pixelXsize,
        'HEIGHT': pixelYsize,
        'EXTENT': '%.10f,%.10f,%.10f,%.10f [%s]'% (xmin, xmax, ymin, ymax, proj),
        'DATA_TYPE': dataTypeNumber,
        'TARGET_CRS': proj,
        'NODATA': -9999,
        'BURN': burnValue,
        'INVERT': False,
        'INIT': None,
        'OPTIONS': '',
        'OUTPUT': rasterOut
    }
    processing.run('gdal:rasterize', params)
    #print(rasterOut, params)

def clipRasterWithRaster(inModelLayer, inRasterPath, outRasterPath):
    projId = inModelLayer.crs().authid()
    extent = inModelLayer.extent()
    xmin = extent.xMinimum()
    xmax = extent.xMaximum()
    ymin = extent.yMinimum()
    ymax = extent.yMaximum()

    processing.run('gdal:cliprasterbyextent', {
        'DATA_TYPE': 0,
        'EXTRA': '',
        'INPUT': inRasterPath,
        'NODATA': None,
        'OPTIONS': '',
        'OUTPUT': outRasterPath,
        'PROJWIN': '%f,%f,%f,%f [%s]'% (xmin, xmax, ymin, ymax, projId)
        # supposed to look like '816737.5,818087.5,6385482.5,6386632.5 [EPSG:2154]'
    })

def convertToPCRasterFormat(pathIn, pathOut, dataType, proj, dataTypeNumber=None):
    if dataTypeNumber == None:
        processing.run('gdal:translate', {
            'INPUT': pathIn,
            'OPTIONS': dataType,
            #'DATA_TYPE': 6,
            'TARGET_CRS': proj,
            'NODATA': None,
            'COPY_SUBDATASETS': False,
            'OUTPUT': pathOut
        })
    else:
        processing.run('gdal:translate', {
            'INPUT': pathIn,
            'OPTIONS': dataType,
            'DATA_TYPE': dataTypeNumber,
            'TARGET_CRS': proj,
            'NODATA': None,
            'COPY_SUBDATASETS': False,
            'OUTPUT': pathOut
        })

def convertToPCRasterLDDFormat(pathIn, pathOut, dataType, proj):
    processing.run('gdal:translate', {
        'INPUT': pathIn,
        'OPTIONS': dataType,
        'EXTRA' : '-mo PCRASTER_VALUESCALE=VS_LDD',
        'DATA_TYPE': 1,
        'TARGET_CRS': proj,
        'NODATA': None,
        'COPY_SUBDATASETS': False,
        'OUTPUT': pathOut
    })

def convertSagaRasterToTif(pathIn, pathOut, proj, dataType=None):
    if dataType == None:
        processing.run('gdal:translate', {
            'INPUT': pathIn,
            'OPTIONS': '',
            #'DATA_TYPE':6,
            'TARGET_CRS': proj,
            'NODATA': None,
            'COPY_SUBDATASETS': False,
            'OUTPUT': pathOut
        })
    else:
        processing.run('gdal:translate', {
            'INPUT': pathIn,
            'OPTIONS': '',
            'DATA_TYPE': dataType,
            'TARGET_CRS': proj,
            'NODATA': None,
            'COPY_SUBDATASETS': False,
            'OUTPUT': pathOut
        })

'''
PCRaster directions (with lddcreate)
7 8 9
4 5 6
1 2 3

Saga directions (with fillsinkswangliu)
7  0  1
6 -1  2
5  4  3
'''
def convertLddDirectionsSagaToPcRaster(raster_in_path, raster_out_path):
    processing.run('gdal:rastercalculator', {
        'BAND_A': 1,
        'FORMULA': '((A==-1)*5) + ((A==0)*8) + ((A==1)*9) + ((A==2)*6) + ((A==3)*3) + '+
                    '((A==4)*2) + ((A==5)*1) + ((A==6)*4) + ((A==7)*7)',
        'INPUT_A': raster_in_path,
        'NO_DATA': None,
        'OPTIONS': '',
        'OUTPUT': raster_out_path,
        'RTYPE': 5
    })

def convertLddDirectionsSagaToPcRasterNumpy(raster_in_path, raster_out_path):
    inGd = gdal.Open(raster_in_path)
    inband1 = inGd.GetRasterBand(1)
    indata1 = BandReadAsArray(inband1)
    inNodata = inband1.GetNoDataValue()

    convArr = {
        -1: 5,
        0: 8,
        1: 9,
        2: 6,
        3: 3,
        4: 2,
        5: 1,
        6: 4,
        7: 7,
        inNodata: inNodata
    }

    indata1 = np.vectorize(convArr.get, otypes=[float])(indata1)
    indata1[np.isnan(indata1)] = inNodata

    driver = gdal.GetDriverByName('GTiff')
    resOut = driver.Create(raster_out_path, inGd.RasterXSize, inGd.RasterYSize, 1, inband1.DataType)
    CopyDatasetInfo(inGd, resOut)
    bandOut = resOut.GetRasterBand(1)
    bandOut.SetNoDataValue(inNodata)
    BandWriteArray(bandOut, indata1)

    inGd = None
    inband1 = None
    resOut = None
    bandOut = None

'''
Grass directions (r.fill.dir with 'grass' output format)
135  90  45
180      360
225  270 315
'''
def convertLddDirectionsGrassToPcRaster(raster_in_path, raster_out_path):
    processing.run('gdal:rastercalculator', {
        'BAND_A': 1,
        'FORMULA': '((A==90)*8) + ((A==45)*9) + ((A==360)*6) + ((A==315)*3) + '+
                    '((A==270)*2) + ((A==225)*1) + ((A==180)*4) + ((A==135)*7)',
        'INPUT_A': raster_in_path,
        'NO_DATA': 255,
        'OPTIONS': '',
        'OUTPUT': raster_out_path,
        'RTYPE': 5
    })

'''
Grass directions (r.watershed drainage output format)
3  2  1
4  0  8
5  6  7
'''
def convertLddDirectionsGrassWatershedToPcRaster(raster_in_path, raster_out_path):
    processing.run('gdal:rastercalculator', {
        'BAND_A': 1,
        'FORMULA': '((A==1)*9) + ((A==2)*8) + ((A==3)*7) + ((A==4)*4) + '+
                    '((A==5)*1) + ((A==6)*2) + ((A==7)*3) + ((A==8)*6) + ((A==0)*5)',
        'INPUT_A': raster_in_path,
        'NO_DATA': 0,
        'OPTIONS': '',
        'OUTPUT': raster_out_path,
        'RTYPE': 5
    })

def fillNoData(raster_in, raster_out, value):
    processing.run('grass7:r.null', {
        '-c': False,
        '-f': False,
        '-i': False,
        '-n': False,
        '-r': False,
        'GRASS_RASTER_FORMAT_META': '',
        'GRASS_RASTER_FORMAT_OPT': '',
        'GRASS_REGION_CELLSIZE_PARAMETER': 0,
        'GRASS_REGION_PARAMETER': None,
        'map': raster_in,
        'null': value,
        'output': raster_out,
        'setnull': ''
    })

def batchConvertToPCRasterFormat(path_in, path_out, proj_info):
    in_raster = gdal.Open(path_in)
    driver = gdal.GetDriverByName('PCRaster')
    out_ds = driver.CreateCopy(path_out, in_raster)
    out_ds.SetProjection(proj_info)
    out_ds.FlushCache()

def reproject(model, pathIn, pathOut, proj):
    pixelXsize = model.rasterUnitsPerPixelX()
    pixelYsize = model.rasterUnitsPerPixelY()
    processing.run('gdal:warpreproject', {
        'INPUT': pathIn,
        'WIDTH': pixelXsize,
        'HEIGHT': pixelYsize,
        'TARGET_CRS': proj,
        'NODATA': None,
        'OUTPUT': pathOut
    })

# this was easy but does not work anymore on QGIS 3.10.1 on Windows...seriously?
def convertToShapefile(raster, vector, proj):
    processing.run('gdal:polygonize', {
        'INPUT': raster,
        'BAND': 1,
        'FIELD': 'DN',
        'TARGET_CRS': proj,
        'EIGHT_CONNECTEDNESS': False,
        'OUTPUT': vector
    })

# reliable way to vectorize a raster
def convertToShapefileGdal(inputRasterPath, outputVectorPath, dem_proj):
    raster_rs  = gdal.Open(inputRasterPath)
    catch_band    = raster_rs.GetRasterBand(1)
    drv           = ogr.GetDriverByName('ESRI Shapefile')
    catchment_ds  = drv.CreateDataSource(outputVectorPath)
    spat_ref      = osr.SpatialReference()
    spat_ref.ImportFromWkt(dem_proj)
    catch_layer   = catchment_ds.CreateLayer('catchment', spat_ref, ogr.wkbPolygon)
    field         = ogr.FieldDefn('ID', ogr.OFTInteger)
    catch_layer.CreateField(field)
    catch_band.FlushCache()
    gdal.Polygonize(catch_band, catch_band, catch_layer, 0, [], callback=None )  # using the catchment map as a mask (2nd arg)
    catchment_ds.Destroy()
    raster_rs = None
    catch_band = None

def clipRasterWithShape(rasterIn, mask, rasterOut, sourceCrs=None, nodata=''):
    processing.run('gdal:cliprasterbymasklayer', {
        'INPUT': rasterIn,
        'MASK': mask,
        'NODATA': nodata,
        'SOURCE_CRS': sourceCrs,
        'ALPHA_BAND': False,
        'CROP_TO_CUTLINE': True,
        'KEEP_RESOLUTION': False,
        'OUTPUT': rasterOut
    })

def fixGeometry(shapeIn, shapeOut):
    processing.run('native:fixgeometries', {
        'INPUT': shapeIn,
        'OUTPUT': shapeOut
    })

def pixelsToPoints(rasterInputPath, outShapePath):
    params = {
        'INPUT_RASTER': rasterInputPath,
        'RASTER_BAND': 1,
        'FIELD_NAME': 'VALUE',
        'OUTPUT': outShapePath
    }
    processing.run('qgis:pixelstopoints', params)
